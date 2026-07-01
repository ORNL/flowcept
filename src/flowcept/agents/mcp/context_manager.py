from contextlib import asynccontextmanager

from flowcept.agents.provenance_schema_manager.context_schema_manager import ContextSchemaManager
from flowcept.agents.provenance_schema_manager.static_schema_builder import (
    SCHEMA_CONTEXT,
    assert_schema_documented,
    build_schema_context,
)
from flowcept.agents.data_query_tools.pandas_utils import load_saved_df
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject
from flowcept.commons.flowcept_dataclasses.blob_object import BlobObject
from flowcept.commons.task_data_preprocess import (
    TelemetrySummary,
    CpuSummary,
    MemorySummary,
    DiskSummary,
    NetworkSummary,
    summarize_task,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.configs import AGENT, AGENT_HOST, AGENT_PORT
from mcp.server.fastmcp import FastMCP

import json
import os.path
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager, BaseAppContext


AGENT_DEBUG = AGENT.get("debug", False)


@dataclass
class FlowceptAppContext(BaseAppContext):
    """
    Context object for holding flowcept-specific state (e.g., tasks data) during the agent's lifecycle.

    Attributes
    ----------
    task_summaries : List[Dict]
        List of summarized task dictionaries.
    critical_tasks : List[Dict]
        List of critical task summaries with tags or anomalies.
    """

    tasks: List[Dict] | None
    task_summaries: List[Dict] | None
    critical_tasks: List[Dict] | None
    df: pd.DataFrame | None
    tasks_schema: Dict | None  # TODO: we dont need to keep the tasks_schema in context, just in the manager's memory.
    value_examples: Dict | None
    tracker_config: Dict | None
    custom_guidance: List[str] | None
    agents: Dict | None

    def __init__(self):
        self.logger = FlowceptLogger()
        self.reset_context()

    def reset_context(self):
        """
        Reset the agent's context to a clean state, initializing a new QA setup.
        """
        self.tasks = []
        self.workflow_msg_obj = {}
        self.objects = []
        self.task_summaries = []
        self.critical_tasks = []
        self.df = pd.DataFrame()
        self.tasks_schema = {}
        self.value_examples = {}
        self.custom_guidance = []
        self.tracker_config = {}
        self.objects_df = pd.DataFrame()
        self.objects_schema = {}
        self.objects_value_examples = {}
        self.workflow_schema_cache = {}
        self.agents = {}

        if AGENT_DEBUG:
            from flowcept.commons.flowcept_logger import FlowceptLogger

            FlowceptLogger().warning("Running agent in DEBUG mode!")
            df_path = "/tmp/current_agent_df.csv"
            if os.path.exists(df_path):
                self.logger.warning("Going to load df into context")
                df = load_saved_df(df_path)
                self.df = df
            if os.path.exists("/tmp/current_tasks_schema.json"):
                with open("/tmp/current_tasks_schema.json") as f:
                    self.tasks_schema = json.load(f)
            if os.path.exists("/tmp/value_examples.json"):
                with open("/tmp/value_examples.json") as f:
                    self.value_examples = json.load(f)


class FlowceptAgentContextManager(BaseAgentContextManager):
    """
    Manages agent context and operations for Flowcept's intelligent task monitoring.

    This class extends BaseAgentContextManager and maintains a rolling buffer of task messages.
    It summarizes and tags tasks, builds a QA index over them, and uses LLM tools to analyze
    task batches periodically.

    Attributes
    ----------
    context : FlowceptAppContext
        Current application context holding task state and QA components.
    msgs_counter : int
        Counter tracking how many task messages have been processed.
    context_chunk_size : int
        Number of task messages to collect before triggering QA index building and LLM analysis.
    qa_manager : FlowceptQAManager
        Utility for constructing QA chains from task summaries.
    """

    def __init__(self):
        self.context = FlowceptAppContext()
        self.tracker_config = dict(max_examples=3, max_str_len=50)
        self.schema_manager = ContextSchemaManager(self.context, self.tracker_config)
        self._seen_activities: dict = {}
        self.msgs_counter = 0
        self.context_chunk_size = 1  # Should be in the settings
        super().__init__(allow_mq_disabled=True)

    def reset_context(self):
        """Reset MCP runtime context and workflow-scoped schema trackers."""
        self.context.reset_context()
        self.schema_manager.reset()
        self._seen_activities = {}
        self.msgs_counter = 0

    def get_workflow_schema_snapshot(self, workflow_id: str):
        """Return the cached schema snapshot for the given workflow, or None.

        Parameters
        ----------
        workflow_id : str
            The workflow whose schema snapshot is requested.
        """
        return self.schema_manager.get_workflow_schema_snapshot(workflow_id)

    def persist_workflow_schema_snapshot(self, workflow_id: str) -> bool:
        """Persist the cached schema snapshot for the given workflow.

        Parameters
        ----------
        workflow_id : str
            The workflow whose schema snapshot should be persisted.
        """
        return self.schema_manager.persist_workflow_schema_snapshot(workflow_id)

    @asynccontextmanager
    async def lifespan(self, app):
        """Validate schema documentation and expose context for the ASGI lifecycle.

        Asserts that all domain-class fields have docstrings, populates ``SCHEMA_CONTEXT``
        for prompt builders, then yields. The MQ consumer is started externally by
        ``FlowceptMCPServer.start()`` — not here.
        """
        assert_schema_documented(
            TaskObject,
            WorkflowObject,
            AgentObject,
            BlobObject,
            TelemetrySummary,
            CpuSummary,
            MemorySummary,
            DiskSummary,
            NetworkSummary,
        )
        SCHEMA_CONTEXT.update(build_schema_context())
        async with super().lifespan(app) as ctx:
            yield ctx

    def message_handler(self, msg_obj: Dict):
        """
        Handle an incoming message and update context accordingly.

        Parameters
        ----------
        msg_obj : Dict
            The incoming message object.

        Returns
        -------
        bool
            True if the message was handled successfully.
        """
        msg_type = msg_obj.get("type", None)
        if msg_type == "workflow":
            # Preserve the user-loaded workflow when the agent/chat runtime emits its own workflow.
            # Compare workflow_ids: if we have a loaded workflow and the incoming message belongs to
            # a different workflow, ignore it so runtime chat/agent workflows never overwrite the
            # explicitly loaded provenance workflow.
            loaded_wf_id = (self.context.workflow_msg_obj or {}).get("workflow_id")
            incoming_wf_id = msg_obj.get("workflow_id")
            if loaded_wf_id and incoming_wf_id and loaded_wf_id != incoming_wf_id:
                self.logger.info("Ignoring runtime workflow (different workflow_id); keeping loaded workflow context.")
                return True
            self.context.workflow_msg_obj = msg_obj
            if WorkflowObject.from_dict(msg_obj).workflow_is_finished():
                self.persist_workflow_schema_snapshot(msg_obj.get("workflow_id"))
            return True

        if msg_type == "agent":
            agent_id = msg_obj.get("agent_id")
            if agent_id:
                self.context.agents[agent_id] = msg_obj
            return True

        if msg_type == "object":
            self.context.objects.append(msg_obj)
            self.schema_manager.update_objects_schema_and_add_to_df(objects=[msg_obj])
            return True

        if msg_type == "task":
            task_msg = TaskObject.from_dict(msg_obj)

            # Filter agent-internal tasks (AI_MODEL_INVOCATION and AGENT_TOOL) that must not
            # pollute the user-workflow DataFrame.  Two cases warrant filtering:
            # 1. The task belongs to this agent (original self-filter).
            # 2. A user workflow is already loaded and this task belongs to a different workflow
            #    — i.e. it was emitted by an external agent (e.g. the chat orchestrator) running
            #    its own session workflow alongside the user's workflow.
            # User workflow tasks that happen to carry AGENT_TOOL (e.g. submit_gridsearch_job)
            # are preserved because their workflow_id matches the loaded workflow.
            if task_msg.subtype in (PROV_AGENT.AI_MODEL_INVOCATION, PROV_AGENT.AGENT_TOOL):
                loaded_wf_id = (self.context.workflow_msg_obj or {}).get("workflow_id")
                task_wf_id = msg_obj.get("workflow_id")
                if task_msg.agent_id == self.agent_id or (loaded_wf_id and task_wf_id != loaded_wf_id):
                    self.logger.debug(
                        f"Ignoring agent-internal task (subtype={task_msg.subtype}, "
                        f"agent={task_msg.agent_id}): {task_msg.activity_id}"
                    )
                    return True

            self.logger.debug("Received task msg!")
            if task_msg.subtype == "call_agent_task":
                from flowcept.instrumentation.task_capture import FlowceptTask

                if task_msg.activity_id == "reset_user_context":
                    self.context.reset_context()
                    self.msgs_counter = 0
                    if self._mq_dao is None:
                        self.logger.warning("MQ is disabled; skipping reset_user_context response message.")
                    else:
                        FlowceptTask(
                            agent_id=self.agent_id,
                            generated={"msg": "Provenance Agent reset context."},
                            subtype=PROV_AGENT.AGENT_TOOL,
                            activity_id="reset_user_context",
                        ).send()
                    return True
                elif task_msg.activity_id == "provenance_query":
                    self.logger.info(
                        "Ignoring legacy provenance_query task; explicit workflow query tools are used instead."
                    )
                    return True

            self.msgs_counter += 1

            self.context.tasks.append(msg_obj)

            task_summary = summarize_task(msg_obj, logger=self.logger)
            self.context.task_summaries.append(task_summary)
            if len(task_summary.get("tags", [])):
                self.context.critical_tasks.append(task_summary)

            if self.msgs_counter > 0 and self.msgs_counter % self.context_chunk_size == 0:
                self.logger.debug(
                    f"Going to add to index! {(self.msgs_counter - self.context_chunk_size, self.msgs_counter)}"
                )
                try:
                    self.schema_manager.update_schema_and_add_to_df(
                        tasks=self.context.task_summaries[
                            self.msgs_counter - self.context_chunk_size : self.msgs_counter
                        ]
                    )
                except Exception as e:
                    task_slice = self.context.task_summaries[
                        self.msgs_counter - self.context_chunk_size : self.msgs_counter
                    ]
                    self.logger.error(f"Could not add these tasks to buffer!\n{task_slice}")
                    self.logger.exception(e)

                activity_id = msg_obj.get("activity_id")
                workflow_id = msg_obj.get("workflow_id")
                if (
                    activity_id
                    and workflow_id
                    and msg_obj.get("used")
                    and msg_obj.get("generated")
                    and activity_id not in self._seen_activities.get(workflow_id, set())
                ):
                    self.schema_manager.update_workflow_schema_cache([msg_obj])
                    self._seen_activities.setdefault(workflow_id, set()).add(activity_id)

                # self.monitor_chunk()

        return True

    def monitor_chunk(self):
        """
        Perform LLM-based analysis on the current chunk of task messages and send the results.
        """
        self.logger.debug(f"Going to begin LLM job! {self.msgs_counter}")
        from flowcept.agents.mcp.mcp_client import run_tool

        result = run_tool("analyze_task_chunk")
        if len(result):
            content = result[0].text
            if content != "Error executing tool":
                if self._mq_dao is None:
                    self.logger.warning("MQ is disabled; skipping monitor message.")
                else:
                    msg = {"type": "flowcept_agent", "info": "monitor", "content": content}
                    self._mq_dao.send_message(msg)
                    self.logger.debug(str(content))
            else:
                self.logger.error(content)


# Exporting the ctx_manager and the mcp_flowcept
ctx_manager = FlowceptAgentContextManager()

agent_transport_security = None
if "allowed_hosts" in AGENT:
    from mcp.server.transport_security import TransportSecuritySettings

    allowed_hosts = list(AGENT.get("allowed_hosts") or [])
    for host in {AGENT_HOST, "localhost", "127.0.0.1", "::1"}:
        for allowed_host in {host, f"{host}:*", f"{host}:{AGENT_PORT}"}:
            if allowed_host not in allowed_hosts:
                allowed_hosts.append(allowed_host)
    agent_transport_security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
    )

mcp_flowcept = FastMCP(
    "FlowceptAgent",
    lifespan=ctx_manager.lifespan,
    stateless_http=True,
    transport_security=agent_transport_security if agent_transport_security else None,
)

EMPTY_DF_MESSAGE = "Current df is empty or null."


def get_df_context(context_kind="tasks"):
    """
    Return active agent DataFrame context objects.

    Returns
    -------
    tuple
        ``(df, schema, value_examples, custom_user_guidance)`` from lifespan context.
    """
    lifespan_context = ctx_manager.context
    if context_kind == "objects":
        df = lifespan_context.objects_df
        schema = lifespan_context.objects_schema
        value_examples = lifespan_context.objects_value_examples
    else:
        df = lifespan_context.df
        schema = lifespan_context.tasks_schema
        value_examples = lifespan_context.value_examples
    custom_user_guidance = lifespan_context.custom_guidance
    return df, schema, value_examples, custom_user_guidance
