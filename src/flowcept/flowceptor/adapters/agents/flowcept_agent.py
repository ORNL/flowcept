import json
import os
from typing import Dict, List

import uvicorn
from langchain.chains.retrieval_qa.base import RetrievalQA
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

from flowcept.configs import AGENT
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.agents.agents_utils import (
    convert_mcp_to_langchain,
    convert_mcp_messages_to_plain_text,
)
from flowcept.flowceptor.adapters.agents.flowcept_llm_prov_capture import (
    invoke_llm,
    invoke_qa_question,
    add_preamble_to_response,
)
from flowcept.flowceptor.adapters.agents.prompts import (
    get_question_prompt,
    BASE_MULTITASK_PROMPT,
    BASE_SINGLETASK_PROMPT,
)
from flowcept.flowceptor.consumers.agent.flowcept_agent_context_manager import FlowceptAgentContextManager
from flowcept.flowceptor.consumers.agent.flowcept_qa_manager import FlowceptQAManager

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")

agent_controller = FlowceptAgentContextManager()
mcp = FastMCP("FlowceptAgent", require_session=True, lifespan=agent_controller.lifespan)

#################################################
# PROMPTS
#################################################


@mcp.prompt()
def single_task_used_generated_prompt(task_data: Dict, question: str) -> list[base.Message]:
    """
    Generate a prompt for analyzing a single task's provenance and resource usage.

    Parameters
    ----------
    task_data : dict
        The task object containing provenance and telemetry fields.
    question : str
        A specific question to ask about the task.

    Returns
    -------
    list of base.Message
        The structured prompt messages for LLM analysis.
    """
    msgs = BASE_SINGLETASK_PROMPT.copy()
    msgs.append(get_question_prompt(question))
    msgs.append(base.UserMessage(f"This is the task object I need you to focus on: \n {task_data}\n"))
    return msgs


@mcp.prompt()
def multi_task_summary_prompt(task_list: List[Dict]) -> List[base.Message]:
    """
    Generate a prompt for analyzing multiple task objects in a workflow.

    Parameters
    ----------
    task_list : list of dict
        A list of task objects with provenance and telemetry data.

    Returns
    -------
    list of base.Message
        The structured prompt messages for the LLM.
    """
    messages = BASE_MULTITASK_PROMPT.copy()
    pretty_tasks = json.dumps(task_list, indent=2, default=str)
    messages.append(base.UserMessage(f"These are the tasks I need you to reason about:\n\n{pretty_tasks}\n\n"))
    return messages


@mcp.prompt()
def multi_task_qa_prompt(question: str) -> List[base.Message]:
    """
    Generate a prompt for asking a specific question about multiple tasks.

    Parameters
    ----------
    question : str
        The user's query about task data.

    Returns
    -------
    list of base.Message
        Prompt messages structured for the LLM.
    """
    messages = BASE_MULTITASK_PROMPT.copy()
    messages.append(get_question_prompt(question))
    return messages


#################################################
# TOOLS
#################################################


@mcp.tool()
def analyze_task_chunk() -> str:
    """
    Analyze a recent chunk of tasks using an LLM to detect patterns or anomalies.

    Returns
    -------
    str
        LLM-generated analysis of the selected task chunk.
    """
    LAST_K = 5  # TODO make this dynamic from config
    ctx = mcp.get_context()
    task_list = ctx.request_context.lifespan_context.task_summaries[:-LAST_K]
    agent_controller.logger.debug(f"N Tasks = {len(task_list)}")
    if not task_list:
        return "No tasks available."

    messages = multi_task_summary_prompt(task_list)
    langchain_messages = convert_mcp_to_langchain(messages)
    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp, task_data=None)
    agent_controller.logger.debug(f"Result={result}")
    return result


@mcp.tool()
def ask_about_tasks_buffer(question: str) -> str:
    """
    Use a QA chain to answer a question about the current task buffer.

    Parameters
    ----------
    question : str
        The question to ask about the buffered tasks.

    Returns
    -------
    str
        Answer from the QA chain or an error message.
    """
    ctx = mcp.get_context()
    qa_chain = build_qa_chain_from_ctx(ctx)
    if not qa_chain:
        return "No tasks available."

    messages = multi_task_qa_prompt(question)

    try:
        query_str = convert_mcp_messages_to_plain_text(messages)
    except Exception as e:
        agent_controller.logger.exception(e)
        return f"An internal error happened: {e}"

    response = invoke_qa_question(qa_chain, query_str=query_str)
    agent_controller.logger.debug(f"Response={response}")
    return response


def build_qa_chain_from_ctx(ctx) -> RetrievalQA:
    """
    Build or retrieve a QA chain from the current request context.

    Parameters
    ----------
    ctx : RequestContext
        The current MCP request context.

    Returns
    -------
    RetrievalQA or None
        A QA chain built from vectorstore metadata, or None if unavailable.
    """
    qa_chain = ctx.request_context.lifespan_context.qa_chain
    if not qa_chain:
        vectorstore_path = ctx.request_context.lifespan_context.vectorstore_path
        if not vectorstore_path:
            return None
        agent_controller.logger.debug(f"Path: {vectorstore_path}")
        qa_chain = FlowceptQAManager.build_qa_chain_from_vectorstore_path(vectorstore_path)
        if not qa_chain:
            return None
    return qa_chain


@mcp.tool()
def get_latest(n: int = None) -> str:
    """
    Return the most recent task(s) from the task buffer.

    Parameters
    ----------
    n : int, optional
        Number of most recent tasks to return. If None, return only the latest.

    Returns
    -------
    str
        JSON-encoded task(s).
    """
    ctx = mcp.get_context()
    tasks = ctx.request_context.lifespan_context.tasks
    if not tasks:
        return "No tasks available."
    if n is None:
        return json.dumps(tasks[-1])
    return json.dumps(tasks[-n])


@mcp.tool()
def check_liveness() -> str:
    """
    Confirm the agent is alive and responding.

    Returns
    -------
    str
        Liveness status string.
    """
    return f"I'm {mcp.name} and I'm ready!"


@mcp.tool()
def check_llm() -> str:
    """
    Check connectivity and response from the LLM backend.

    Returns
    -------
    str
        LLM response, formatted with MCP metadata.
    """
    messages = [base.UserMessage("Hi, are you working properly?")]

    langchain_messages = convert_mcp_to_langchain(messages)
    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp)

    return result


@mcp.tool()
def ask_about_latest_task(question) -> str:
    """
    Ask a question specifically about the latest task in the buffer.

    Parameters
    ----------
    question : str
        A user-defined question to analyze the latest task.

    Returns
    -------
    str
        Response from the LLM based on the latest task.
    """
    ctx = mcp.get_context()
    tasks = ctx.request_context.lifespan_context.task_summaries
    if not tasks:
        return "No tasks available."
    task_data = tasks[-1]

    messages = single_task_used_generated_prompt(task_data, question)

    langchain_messages = convert_mcp_to_langchain(messages)

    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp, task_data)
    return result


def main():
    """
    Start the MCP server.
    """
    f = Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False).start()
    f.logger.info(f"This section's workflow_id={Flowcept.current_workflow_id}")
    setattr(mcp, "workflow_id", f.current_workflow_id)
    uvicorn.run(
        mcp.streamable_http_app, host=AGENT.get("mcp_host", "0.0.0.0"), port=AGENT.get("mcp_port", 8000), lifespan="on"
    )


if __name__ == "__main__":
    main()
