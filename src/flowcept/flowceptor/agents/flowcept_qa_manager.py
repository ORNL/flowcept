# from typing import Dict, List
#
# from langchain.chains.retrieval_qa.base import RetrievalQA, BaseRetrievalQA
# from langchain_community.embeddings import HuggingFaceEmbeddings
# from langchain_community.vectorstores import FAISS
# from langchain.schema import Document
# from langchain_core.language_models import LLM
#
# from flowcept.commons.flowcept_logger import FlowceptLogger
# from flowcept.flowceptor.agents import build_llm_model
#
#
# # TODO If all methods are static, this doesnt need to be a class.
# class FlowceptQAManager(object):
#     """
#     Manager for building and loading question-answering (QA) chains using LangChain.
#
#     This utility constructs a `RetrievalQA` chain by converting task dictionaries into
#     `Document` objects, embedding them with HuggingFace, storing them in a FAISS vectorstore,
#     and returning a ready-to-query QA pipeline.
#
#     Attributes
#     ----------
#     embedding_model : HuggingFaceEmbeddings
#         The default embedding model used to embed documents into vector representations.
#     """
#
#     embedding_model = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
#     vector_store = None
#     qa_chain: BaseRetrievalQA = None
#
#     @staticmethod
#     def add_to_index(docs: List[Dict] = None, llm: LLM = None):
#         """
#         Build a RetrievalQA chain from a list of task dictionaries.
#
#         Parameters
#         ----------
#         docs : List[Dict], optional
#             A list of task dictionaries to be converted into retrievable documents.
#         llm : LLM, optional
#             The language model to use for the QA chain. If None, a default model is built.
#
#         Returns
#         -------
#         dict
#             A dictionary containing:
#             - 'qa_chain': the constructed RetrievalQA chain
#             - 'path': local path where the FAISS vectorstore is saved
#
#         Notes
#         -----
#         If no documents are provided, the method returns None.
#         """
#         if not len(docs):
#             return None
#
#         if llm is None:
#             llm = build_llm_model()
#
#         documents = []
#         for d in docs:
#             content = str(d)  # convert the dict to a string
#             metadata = {"task_id": d.get("task_id", "unknown")}
#             documents.append(Document(page_content=content, metadata=metadata))
#
#         FlowceptLogger().debug(f"Number of documents to index: {len(documents)}")
#         if FlowceptQAManager.vector_store is None:
#             FlowceptLogger().debug(f"vector_store is none, so we are creating it.")
#             FlowceptQAManager.vector_store = FAISS.from_documents(documents=documents, embedding=FlowceptQAManager.embedding_model)
#             retriever = FlowceptQAManager.vector_store.as_retriever()
#             FlowceptQAManager.qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)
#         else:
#             FlowceptLogger().debug(f"vector_store is not none, so we are expanding it.")
#             FlowceptQAManager.vector_store.add_documents(documents)
#
#         path = "/tmp/qa_index"
#         FlowceptQAManager.vector_store.save_local(path)
#
#     @staticmethod
#     def _load_qa_chain(path, llm=None, embedding_model=None) -> RetrievalQA:
#         if embedding_model is None:
#             embedding_model = FlowceptQAManager.embedding_model
#         if llm is None:
#             llm = build_llm_model()
#
#         vectorstore = FAISS.load_local(path, embeddings=embedding_model, allow_dangerous_deserialization=True)
#
#         retriever = vectorstore.as_retriever()
#
#         return RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)
#
#     @staticmethod
#     def build_qa_chain_from_vectorstore_path(vectorstore_path, llm=None) -> RetrievalQA:
#         """
#         Build a RetrievalQA chain from an existing vectorstore path.
#
#         Parameters
#         ----------
#         vectorstore_path : str
#             Path to the FAISS vectorstore previously saved to disk.
#         llm : LLM, optional
#             Language model to use. If None, a default model is built.
#
#         Returns
#         -------
#         RetrievalQA
#             A RetrievalQA chain constructed using the loaded vectorstore.
#         """
#         if llm is None:
#             llm = build_llm_model()  # TODO: consider making this llm instance static
#         qa_chain = FlowceptQAManager._load_qa_chain(
#             path=vectorstore_path,  # Only here we really need the QA. We might no
#             llm=llm,
#             embedding_model=FlowceptQAManager.embedding_model,
#         )
#         return qa_chain
