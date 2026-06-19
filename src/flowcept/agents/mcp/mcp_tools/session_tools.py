"""Session-level MCP tools: liveness, LLM check, guidance recording, and context reset."""

import json
from typing import List

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.llm.builders import build_llm_model
from flowcept.agents.mcp.context_manager import mcp_flowcept


@mcp_flowcept.tool()
def get_latest(n: int = None) -> str:
    """Return the most recent task(s) from the task buffer.

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
    """Confirm the agent is alive and responding.

    Returns
    -------
    str
        Liveness status string.
    """
    return f"I'm {mcp_flowcept.name} and I'm ready!"


@mcp_flowcept.tool()
def check_llm() -> str:
    """Check connectivity and response from the LLM backend.

    Returns
    -------
    str
        LLM response.
    """
    llm = build_llm_model()
    return llm("Hello?")


@mcp_flowcept.tool()
def record_guidance(message: str) -> ToolResult:
    """Record a custom guidance message in agent memory.

    Parameters
    ----------
    message : str
        Guidance text to record.

    Returns
    -------
    ToolResult
    """
    ctx = mcp_flowcept.get_context()
    message = message.replace("@record", "")
    custom_guidance: List = ctx.request_context.lifespan_context.custom_guidance
    custom_guidance.append(message)
    return ToolResult(code=201, result=f"Ok. I recorded in my memory: {message}")


@mcp_flowcept.tool()
def show_records() -> ToolResult:
    """List all recorded user guidance.

    Returns
    -------
    ToolResult
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
    """Reset all recorded user guidance.

    Returns
    -------
    ToolResult
    """
    try:
        ctx = mcp_flowcept.get_context()
        ctx.request_context.lifespan_context.custom_guidance = []
        return ToolResult(code=201, result="Custom guidance reset.")
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def reset_context() -> ToolResult:
    """Reset all agent context.

    Returns
    -------
    ToolResult
    """
    try:
        ctx = mcp_flowcept.get_context()
        ctx.request_context.lifespan_context.reset_context()
        return ToolResult(code=201, result="Context reset.")
    except Exception as e:
        return ToolResult(code=499, result=str(e))
