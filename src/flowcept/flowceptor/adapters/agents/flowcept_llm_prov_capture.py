import inspect
from typing import List, Union, Dict

from langchain.chains.retrieval_qa.base import RetrievalQA
from langchain_community.callbacks import get_openai_callback
from langchain_core.language_models import LLM
from langchain_core.messages import HumanMessage, AIMessage

from flowcept.flowceptor.adapters.agents.agents_utils import build_llm_model
from flowcept.instrumentation.task_capture import FlowceptTask


def add_preamble_to_response(response, mcp, task_data=None):
    """
    Add workflow/task-related metadata as a preamble to the LLM response.

    Parameters
    ----------
    response : str
        The LLM response text.
    mcp : Any
        The agent or workflow object, expected to have an optional `workflow_id` attribute.
    task_data : dict, optional
        Dictionary containing task metadata such as `workflow_id` and `task_id`.

    Returns
    -------
    str
        The response string prefixed with workflow/task metadata.
    """
    agent_id_str = ""
    if hasattr(mcp, "workflow_id"):
        agent_id = getattr(mcp, "workflow_id")
        agent_id_str = f"agent_id={agent_id}, "
    task_data_str = ""
    if task_data:
        task_data_str = f"workflow_id={task_data.get("workflow_id")}, task_id={task_data.get("task_id")}\n"
    result = f"{agent_id_str}{task_data_str}Response:\n\n{response}"
    return result


def invoke_llm(messages: List[Union[HumanMessage, AIMessage]], llm: LLM = None, activity_id=None) -> str:
    """
    Invoke an LLM with a list of chat-style messages and return its response.

    Parameters
    ----------
    messages : List[Union[HumanMessage, AIMessage]]
        The list of messages forming the conversation history for the LLM.
    llm : LLM, optional
        An instance of a LangChain-compatible LLM. If None, a default model is built.
    activity_id : str, optional
        An optional identifier for the activity, used for Flowcept instrumentation.

    Returns
    -------
    str
        The LLM's text response.
    """
    if llm is None:
        llm = build_llm_model()
    if activity_id is None:
        activity_id = inspect.stack()[1].function

    used = {"messages": [{"role": msg.type, "content": msg.content} for msg in messages]}

    llm_metadata = _extract_llm_metadata(llm)

    with FlowceptTask(
        activity_id=activity_id, used=used, custom_metadata={"llm_metadata": llm_metadata}, subtype="llm_query"
    ) as t:
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
    Query a RetrievalQA chain with a given question and return the response.

    Parameters
    ----------
    qa_chain : RetrievalQA
        The QA chain object to invoke.
    query_str : str
        The question to ask the QA chain.
    activity_id : str, optional
        An optional identifier for the activity, used for Flowcept instrumentation.

    Returns
    -------
    str
        The textual result from the QA chain.
    """
    used = {"message": query_str}
    qa_chain_metadata = _extract_qa_chain_metadata(qa_chain)
    with FlowceptTask(
        activity_id=activity_id,
        used=used,
        subtype="llm_query",
        custom_metadata={"qa_chain_metadata": qa_chain_metadata},
    ) as t:
        with get_openai_callback() as cb:
            response = dict(qa_chain({"query": f"{query_str}"}))  # TODO bug?
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


def _extract_llm_metadata(llm: LLM) -> Dict:
    """
    Extract metadata from a LangChain LLM instance.

    Parameters
    ----------
    llm : LLM
        The language model instance.

    Returns
    -------
    dict
        Dictionary containing class name, module, model name, and configuration if available.
    """
    llm_metadata = {
        "class_name": llm.__class__.__name__,
        "module": llm.__class__.__module__,
        "model_name": getattr(llm, "model_name", None),
        "config": llm.dict() if hasattr(llm, "dict") else {},
    }
    return llm_metadata


def _extract_qa_chain_metadata(qa_chain: RetrievalQA) -> Dict:
    """
    Extract metadata from a RetrievalQA chain, including LLM and retriever details.

    Parameters
    ----------
    qa_chain : RetrievalQA
        The QA chain to extract metadata from.

    Returns
    -------
    dict
        Metadata dictionary including QA chain class name, retriever details, and optionally LLM metadata.
    """
    retriever = getattr(qa_chain, "retriever", None)
    retriever_metadata = {
        "class_name": retriever.__class__.__name__ if retriever else None,
        "module": retriever.__class__.__module__ if retriever else None,
        "vectorstore_type": getattr(retriever, "vectorstore", None).__class__.__name__
        if hasattr(retriever, "vectorstore")
        else None,
        "retriever_config": retriever.__dict__ if retriever else {},
    }
    metadata = {
        "qa_chain_class": qa_chain.__class__.__name__,
        "retriever": retriever_metadata,
    }
    llm = getattr(qa_chain, "llm", None)
    if llm:
        metadata["llm"] = _extract_llm_metadata(llm)

    return metadata
