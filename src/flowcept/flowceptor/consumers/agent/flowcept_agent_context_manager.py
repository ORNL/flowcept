from dataclasses import dataclass
from typing import Dict, List

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager, BaseAppContext
from langchain.chains.retrieval_qa.base import BaseRetrievalQA
from langchain_community.embeddings import HuggingFaceEmbeddings

from flowcept.flowceptor.consumers.agent import client_agent
from flowcept.flowceptor.consumers.agent.flowcept_qa_manager import FlowceptQAManager
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
    qa_chain : BaseRetrievalQA
        The QA chain used for question-answering over task summaries.
    vectorstore_path : str
        Path to the persisted vectorstore used by the QA system.
    embedding_model : HuggingFaceEmbeddings
        The embedding model used to generate vector representations for tasks.
    """

    task_summaries: List[Dict]
    critical_tasks: List[Dict]
    qa_chain: BaseRetrievalQA
    vectorstore_path: str
    embedding_model: HuggingFaceEmbeddings


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
        self.context_size = 5
        self.qa_manager = FlowceptQAManager()

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
        if msg_type == "task":
            self.msgs_counter += 1
            self.logger.debug("Received task msg!")
            self.context.tasks.append(msg_obj)

            self.logger.debug(f"This is QA! {self.context.qa_chain}")

            task_summary = summarize_task(msg_obj)
            self.context.task_summaries.append(task_summary)
            if len(task_summary.get("tags", [])):
                self.context.critical_tasks.append(task_summary)

            if self.msgs_counter > 0 and self.msgs_counter % self.context_size == 0:
                self.build_qa_index()

                self.monitor_chunk()

        return True

    def monitor_chunk(self):
        """
        Perform LLM-based analysis on the current chunk of task messages and send the results.
        """
        self.logger.debug(f"Going to begin LLM job! {self.msgs_counter}")
        result = client_agent.run_tool("analyze_task_chunk")
        if len(result):
            content = result[0].text
            if content != "Error executing tool":
                msg = {"type": "flowcept_agent", "info": "monitor", "content": content}
                self._mq_dao.send_message(msg)
                self.logger.debug(str(content))
            else:
                self.logger.error(content)

    def build_qa_index(self):
        """
        Build a new QA index from the current list of task summaries.
        """
        self.logger.debug(f"Going to begin QA Build! {self.msgs_counter}")
        try:
            qa_chain_result = self.qa_manager.build_qa(docs=self.context.task_summaries)

            self.context.qa_chain = qa_chain_result.get("qa_chain")
            self.context.vectorstore_path = qa_chain_result.get("path")

            self.logger.debug(f"Built QA! {self.msgs_counter}")
            assert self.context.qa_chain is not None
            self.logger.debug(f"This is QA! {self.context.qa_chain}")
            self.logger.debug(f"This is QA path! {self.context.vectorstore_path}")
        except Exception as e:
            self.logger.exception(e)

    def reset_context(self):
        """
        Reset the agent's context to a clean state, initializing a new QA setup.
        """
        self.context = FlowceptAppContext(
            tasks=[],
            task_summaries=[],
            critical_tasks=[],
            qa_chain=None,
            vectorstore_path=None,
            embedding_model=FlowceptQAManager.embedding_model,
        )
