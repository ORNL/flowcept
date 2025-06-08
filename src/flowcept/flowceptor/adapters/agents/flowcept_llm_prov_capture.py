import inspect
from typing import List, Union, Dict

from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_community.callbacks import get_openai_callback
from langchain_core.language_models import LLM
from langchain_core.messages import HumanMessage, AIMessage

from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.agents.agents_utils import build_llm_model
from flowcept.instrumentation.task_capture import FlowceptTask


def invoke_llm(messages: List[Union[HumanMessage, AIMessage]], llm: LLM=None, activity_id=None) -> str:
    """
    Invoke the LLM and return the response string.
    """
    if llm is None:
        llm = build_llm_model()
    if activity_id is None:
        activity_id = inspect.stack()[1].function

    used = {"messages": [{"role": msg.type, "content": msg.content} for msg in messages]}

    llm_metadata = extract_llm_metadata(llm)

    with FlowceptTask(activity_id=activity_id, used=used, custom_metadata={"llm_metadata": llm_metadata}) as t:
        with get_openai_callback() as cb:
            response = llm.invoke(messages)
            generated = {
                "text_response": response,
                "total_tokens": cb.total_tokens,
                "prompt_tokens": cb.prompt_tokens,
                "completion_tokens": cb.completion_tokens,
                "cost": cb.total_cost,
            }
            t.end(generated)
            return response


def invoke_qa_question(qa_chain: RetrievalQA, query_str: str, activity_id=None) -> str:
    """
    Invoke a QA chain with the given messages and return the response string.
    """
    used = {"message": query_str}
    qa_chain_metadata = extract_qa_chain_metadata(qa_chain)
    with FlowceptTask(activity_id=activity_id, used=used, subtype="llm_qa_chain_query",
                      custom_metadata={"qa_chain_metadata": qa_chain_metadata}) as t:
        with get_openai_callback() as cb:
            response = dict(qa_chain({"query": f"{query_str}"})) # TODO bug?
            text_response = response.pop("result")
            generated = {
                "response": response,
                "text_response": text_response,
                "total_tokens": cb.total_tokens,
                "prompt_tokens": cb.prompt_tokens,
                "completion_tokens": cb.completion_tokens,
                "cost": cb.total_cost,
            }
            t.end(generated)
            return text_response

def extract_llm_metadata(llm: LLM) -> Dict:
    llm_metadata = {
        "class_name": llm.__class__.__name__,
        "module": llm.__class__.__module__,
        "model_name": getattr(llm, "model_name", None),
        "config": llm.dict() if hasattr(llm, "dict") else {},
    }
    return llm_metadata


def extract_qa_chain_metadata(qa_chain: RetrievalQA) -> Dict:
    retriever = getattr(qa_chain, "retriever", None)
    retriever_metadata = {
        "class_name": retriever.__class__.__name__ if retriever else None,
        "module": retriever.__class__.__module__ if retriever else None,
        "vectorstore_type": getattr(retriever, "vectorstore", None).__class__.__name__
        if hasattr(retriever, "vectorstore") else None,
        "retriever_config": retriever.__dict__ if retriever else {},
    }
    metadata = {
        "qa_chain_class": qa_chain.__class__.__name__,
        "retriever": retriever_metadata,
    }
    llm = getattr(qa_chain, "llm", None)
    if llm:
        metadata["llm"] = extract_llm_metadata(llm)

    return metadata
