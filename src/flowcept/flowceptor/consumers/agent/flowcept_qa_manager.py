from typing import Dict, List

from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
from langchain_core.language_models import LLM

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.agents.agents_utils import build_llm_model


# TODO if all methods are static, this doesnt need to be a class.
class FlowceptQAManager(object):

    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    @staticmethod
    def build_qa(docs: List[Dict] = None, llm: LLM = None):
        if not len(docs):
            return None

        if llm is None:
            llm = build_llm_model()

        documents = []
        for d in docs:
            content = str(d)  # convert the dict to a string
            metadata = {"task_id": d.get("task_id", "unknown")}
            documents.append(Document(page_content=content, metadata=metadata))

        FlowceptLogger().debug(f"Number of documents to index: {len(documents)}")
        vectorstore = FAISS.from_documents(documents=documents, embedding=FlowceptQAManager.embedding_model)
        path = "/tmp/qa_index"
        vectorstore.save_local(path)

        retriever = vectorstore.as_retriever()
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
            return_source_documents=True
        )

        return {"qa_chain": qa_chain, "path": path}

    @staticmethod
    def _load_qa_chain(path, llm=None, embedding_model=None) -> RetrievalQA:
        if embedding_model is None:
            embedding_model = FlowceptQAManager.embedding_model
        if llm is None:
            llm = build_llm_model()

        vectorstore = FAISS.load_local(
            path,
            embeddings=embedding_model,
            allow_dangerous_deserialization=True
        )

        retriever = vectorstore.as_retriever()

        return RetrievalQA.from_chain_type(
            llm=llm,
            retriever=retriever,
            return_source_documents=True
        )

    @staticmethod
    def build_qa_chain_from_vectorstore_path(vectorstore_path, llm=None) -> RetrievalQA:
        if llm is None:
            llm = build_llm_model() # TODO: consider making this llm instance static
        qa_chain = FlowceptQAManager._load_qa_chain(
            path=vectorstore_path,  # Only here we really need the QA. We might no
            llm=llm,
            embedding_model=FlowceptQAManager.embedding_model
        )
        return qa_chain
