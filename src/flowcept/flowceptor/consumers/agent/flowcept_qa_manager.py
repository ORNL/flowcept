from typing import Dict, List

from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document
from langchain_core.language_models import LLM

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.agents.agents_utils import build_llm_model


# TODO If all methods are static, this doesnt need to be a class.
class FlowceptQAManager(object):
    """
    Manager for building and loading question-answering (QA) chains using LangChain.

    This utility constructs a `RetrievalQA` chain by converting task dictionaries into
    `Document` objects, embedding them with HuggingFace, storing them in a FAISS vectorstore,
    and returning a ready-to-query QA pipeline.

    Attributes
    ----------
    embedding_model : HuggingFaceEmbeddings
        The default embedding model used to embed documents into vector representations.
    """

    embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    @staticmethod
    def build_qa(docs: List[Dict] = None, llm: LLM = None):
        """
        Build a RetrievalQA chain from a list of task dictionaries.

        Parameters
        ----------
        docs : List[Dict], optional
            A list of task dictionaries to be converted into retrievable documents.
        llm : LLM, optional
            The language model to use for the QA chain. If None, a default model is built.

        Returns
        -------
        dict
            A dictionary containing:
            - 'qa_chain': the constructed RetrievalQA chain
            - 'path': local path where the FAISS vectorstore is saved

        Notes
        -----
        If no documents are provided, the method returns None.
        """
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
        qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)

        return {"qa_chain": qa_chain, "path": path}

    @staticmethod
    def _load_qa_chain(path, llm=None, embedding_model=None) -> RetrievalQA:
        if embedding_model is None:
            embedding_model = FlowceptQAManager.embedding_model
        if llm is None:
            llm = build_llm_model()

        vectorstore = FAISS.load_local(path, embeddings=embedding_model, allow_dangerous_deserialization=True)

        retriever = vectorstore.as_retriever()

        return RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)

    @staticmethod
    def build_qa_chain_from_vectorstore_path(vectorstore_path, llm=None) -> RetrievalQA:
        """
        Build a RetrievalQA chain from an existing vectorstore path.

        Parameters
        ----------
        vectorstore_path : str
            Path to the FAISS vectorstore previously saved to disk.
        llm : LLM, optional
            Language model to use. If None, a default model is built.

        Returns
        -------
        RetrievalQA
            A RetrievalQA chain constructed using the loaded vectorstore.
        """
        if llm is None:
            llm = build_llm_model()  # TODO: consider making this llm instance static
        qa_chain = FlowceptQAManager._load_qa_chain(
            path=vectorstore_path,  # Only here we really need the QA. We might no
            llm=llm,
            embedding_model=FlowceptQAManager.embedding_model,
        )
        return qa_chain
