import json
from typing import List

from flowcept.agents.agents_utils import build_llm_model, ToolResult
from flowcept.agents.flowcept_ctx_manager import mcp_flowcept
from flowcept.agents.prompts.general_prompts import ROUTING_PROMPT, SMALL_TALK_PROMPT

from flowcept.agents.tools.in_memory_queries.in_memory_queries_tools import run_df_query


@mcp_flowcept.tool()
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
    ctx = mcp_flowcept.get_context()
    tasks = ctx.request_context.lifespan_context.tasks
    if not tasks:
        return "No tasks available."
    if n is None:
        return json.dumps(tasks[-1])
    return json.dumps(tasks[-n])


@mcp_flowcept.tool()
def check_liveness() -> str:
    """
    Confirm the agent is alive and responding.

    Returns
    -------
    str
        Liveness status string.
    """
    return f"I'm {mcp_flowcept.name} and I'm ready!"


@mcp_flowcept.tool()
def check_llm() -> str:
    """
    Check connectivity and response from the LLM backend.

    Returns
    -------
    str
        LLM response, formatted with MCP metadata.
    """
    llm = build_llm_model()
    response = llm("Hello?")
    return response


@mcp_flowcept.tool()
def record_guidance(message: str) -> ToolResult:
    """
    Record guidance tool.
    """
    ctx = mcp_flowcept.get_context()
    message = message.replace("@record", "")
    custom_guidance: List = ctx.request_context.lifespan_context.custom_guidance
    custom_guidance.append(message)

    return ToolResult(code=201, result=f"Ok. I recorded in my memory: {message}")


@mcp_flowcept.tool()
def show_records() -> ToolResult:
    """
    Lists all recorded user guidance.
    """
    try:
        ctx = mcp_flowcept.get_context()
        custom_guidance: List = ctx.request_context.lifespan_context.custom_guidance
        if not custom_guidance:
            message = "There is no recorded user guidance."
        else:
            message = "This is the list of custom guidance I have in my memory:\n"
            message += "\n".join(f" - {msg}" for msg in custom_guidance)

        return ToolResult(code=201, result=message)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def reset_records() -> ToolResult:
    """
    Resets all recorded user guidance.
    """
    try:
        ctx = mcp_flowcept.get_context()
        ctx.request_context.lifespan_context.custom_guidance = []
        return ToolResult(code=201, result="Custom guidance reset.")
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def prompt_handler(message: str) -> ToolResult:
    """
    Routes a user message using an LLM to classify its intent.

    Parameters
    ----------
    message : str
        User's natural language input.

    Returns
    -------
    TextContent
        The AI response or routing feedback.
    """
    df_key_words = ["df", "save", "result = df", "reset context"]
    for key in df_key_words:
        if key in message:
            return run_df_query(llm=None, query=message, plot=False)

    if "@record" in message:
        return record_guidance(message)
    if "@show records" in message:
        return show_records()
    if "@reset records" in message:
        return reset_records(message)

    llm = build_llm_model()

    prompt = ROUTING_PROMPT + message
    route = llm.invoke(prompt)

    if route == "small_talk":
        prompt = SMALL_TALK_PROMPT + message
        response = llm.invoke(prompt)
        return ToolResult(code=201, result=response)
    elif route == "in_context_query":
        return run_df_query(llm, message, plot=False)
    elif route == "plot":
        return run_df_query(llm, message, plot=True)
    elif route == "historical_prov_query":
        return ToolResult(code=201, result="We need to query the Provenance Database. Feature coming soon.")
    elif route == "in_chat_query":
        prompt = SMALL_TALK_PROMPT + message
        response = llm.invoke(prompt)
        return ToolResult(code=201, result=response)
    else:
        return ToolResult(code=404, result="I don't know how to route.")
