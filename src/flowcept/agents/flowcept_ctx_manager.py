from flowcept.agents.dynamic_schema_tracker import DynamicSchemaTracker
from flowcept.agents.tools.in_memory_queries.pandas_agent_utils import load_saved_df
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from mcp.server.fastmcp import FastMCP

import json
import os.path
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager, BaseAppContext


from flowcept.agents import agent_client
from flowcept.commons.task_data_preprocess import summarize_task


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
        self.context: FlowceptAppContext = None
        self.tracker_config = dict(max_examples=3, max_str_len=50)
        self.schema_tracker = DynamicSchemaTracker(**self.tracker_config)
        self.msgs_counter = 0
        self.context_chunk_size = 1  # Should be in the settings
        super().__init__()

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
        print("Received:", msg_obj)
        msg_type = msg_obj.get("type", None)
        if msg_type == "task":
            task_msg = TaskObject.from_dict(msg_obj)
            if task_msg.subtype == "llm_task" and task_msg.agent_id == self.agent_id:
                self.logger.info(f"Going to ignore our own LLM messages: {task_msg}")
                return True

            self.msgs_counter += 1
            self.logger.debug("Received task msg!")
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
                    self.update_schema_and_add_to_df(
                        tasks=self.context.task_summaries[
                            self.msgs_counter - self.context_chunk_size : self.msgs_counter
                        ]
                    )
                except Exception as e:
                    self.logger.error(
                        f"Could not add these tasks to buffer!\n"
                        f"{
                            self.context.task_summaries[self.msgs_counter - self.context_chunk_size : self.msgs_counter]
                        }"
                    )
                    self.logger.exception(e)

                # self.monitor_chunk()

        return True

    def update_schema_and_add_to_df(self, tasks: List[Dict]):
        """Update the schema and add to the DataFrame in context."""
        self.schema_tracker.update_with_tasks(tasks)
        self.context.tasks_schema = self.schema_tracker.get_schema()
        self.context.value_examples = self.schema_tracker.get_example_values()

        _df = pd.json_normalize(tasks)
        self.context.df = pd.concat([self.context.df, pd.DataFrame(_df)], ignore_index=True)

    def monitor_chunk(self):
        """
        Perform LLM-based analysis on the current chunk of task messages and send the results.
        """
        self.logger.debug(f"Going to begin LLM job! {self.msgs_counter}")
        result = agent_client.run_tool("analyze_task_chunk")
        if len(result):
            content = result[0].text
            if content != "Error executing tool":
                msg = {"type": "flowcept_agent", "info": "monitor", "content": content}
                self._mq_dao.send_message(msg)
                self.logger.debug(str(content))
            else:
                self.logger.error(content)

    def reset_context(self):
        """
        Reset the agent's context to a clean state, initializing a new QA setup.
        """
        self.context = FlowceptAppContext(
            tasks=[],
            task_summaries=[],
            critical_tasks=[],
            df=pd.DataFrame(),
            tasks_schema={},
            value_examples={},
            tracker_config=self.tracker_config,
        )
        DEBUG = True  # TODO debugging!
        if DEBUG:
            self.logger.warning("Running agent in DEBUG mode!")
            df_path = "/tmp/current_agent_df.csv"
            if os.path.exists(df_path):
                self.logger.warning("Going to load df into context")
                df = load_saved_df(df_path)
                self.context.df = df
            if os.path.exists("/tmp/current_tasks_schema.json"):
                with open("/tmp/current_tasks_schema.json") as f:
                    self.context.tasks_schema = json.load(f)
            if os.path.exists("/tmp/value_examples.json"):
                with open("/tmp/value_examples.json") as f:
                    self.context.value_examples = json.load(f)


# Exporting the ctx_manager and the mcp_flowcept
ctx_manager = FlowceptAgentContextManager()
mcp_flowcept = FastMCP("FlowceptAgent", require_session=False, lifespan=ctx_manager.lifespan, stateless_http=True)
