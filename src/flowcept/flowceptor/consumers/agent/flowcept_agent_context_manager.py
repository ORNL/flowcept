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

    task_summaries: List[Dict]
    critical_tasks: List[Dict]
    qa_chain: BaseRetrievalQA
    vectorstore_path: str
    embedding_model: HuggingFaceEmbeddings


class FlowceptAgentContextManager(BaseAgentContextManager):

    def __init__(self):
        super().__init__()
        self.context: FlowceptAppContext = None
        self.reset_context()
        self.msgs_counter = 0
        self.context_size = 5
        self.qa_manager = FlowceptQAManager()

    def message_handler(self, msg_obj: Dict):
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
        self.logger.debug(f"Going to begin LLM job! {self.msgs_counter}")
        result = client_agent.run_tool("analyze_task_chunk")
        if len(result):
            content = result[0].text
            if content != "Error executing tool":
                msg = {
                    "type": "flowcept_agent",
                    "info": "monitor",
                    "content": content
                }
                self._mq_dao.send_message(msg)
                self.logger.debug(str(content))
            else:
                self.logger.error(content)

    def build_qa_index(self):
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
        self.context = FlowceptAppContext(tasks=[], task_summaries=[], critical_tasks=[], qa_chain=None, vectorstore_path=None,
                                          embedding_model=FlowceptQAManager.embedding_model)
