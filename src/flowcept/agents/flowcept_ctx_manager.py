from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from mcp.server.fastmcp import FastMCP

import json
import os.path
from dataclasses import dataclass
from typing import Dict, List

import pandas as pd

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager, BaseAppContext


from flowcept.agents import agent_client
from flowcept.commons.task_data_preprocess import summarize_task, update_tasks_summary_schema


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
    tasks_schema: Dict | None # TODO: we dont need to keep the tasks_schema in context, just in the manager's memory.


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
    context_size : int
        Number of task messages to collect before triggering QA index building and LLM analysis.
    qa_manager : FlowceptQAManager
        Utility for constructing QA chains from task summaries.
    """

    def __init__(self):
        super().__init__()
        self.context: FlowceptAppContext = None
        self.reset_context()
        self.msgs_counter = 0
        self.context_size = 1

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
        print(msg_obj)
        msg_type = msg_obj.get("type", None)
        if msg_type == "task":
            task_msg = TaskObject.from_dict(msg_obj)
            if task_msg.subtype == "llm_task" and task_msg.agent_id == self.agent_id:
                self.logger.info(f"Going to ignore our own LLM messages: {task_msg}")
                return True

            self.msgs_counter += 1
            self.logger.debug("Received task msg!")
            self.context.tasks.append(msg_obj)

            task_summary = summarize_task(msg_obj)
            self.context.task_summaries.append(task_summary)
            if len(task_summary.get("tags", [])):
                self.context.critical_tasks.append(task_summary)

            if self.msgs_counter > 0 and self.msgs_counter % self.context_size == 0:
                self.logger.debug(f"Going to add to index! {(self.msgs_counter-self.context_size,self.msgs_counter)}")
                self.update_schema_and_add_to_df(tasks=self.context.task_summaries[self.msgs_counter - self.context_size:self.msgs_counter])
                # self.context.qa_chain = FlowceptQAManager.qa_chain
                # self.monitor_chunk()

        return True

    def update_schema_and_add_to_df(self, tasks: List[Dict]):
        self.context.tasks_schema = update_tasks_summary_schema(self.context.task_summaries, self.context.tasks_schema)
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
            df=None,
            tasks_schema={},
        )
        DEBUG = False  # TODO debugging!!
        if DEBUG:
            if os.path.exists("/tmp/current_agent_df.csv"):
                self.logger.warning("We are debugging! -- Going to load df into context")
                df = pd.read_csv("/tmp/current_agent_df.csv", index_col=False)
                self.context.df = df
            if os.path.exists("/tmp/current_tasks_schema.json"):
                with open("/tmp/current_tasks_schema.json") as f:
                    self.context.tasks_schema = json.load(f)


# Exporting the ctx_manager and the mcp_flowcept
ctx_manager = FlowceptAgentContextManager()
mcp_flowcept = FastMCP("FlowceptAgent", require_session=False,
                       lifespan=ctx_manager.lifespan,
                       stateless_http=True)
