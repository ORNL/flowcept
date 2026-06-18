"""Session-level MCP tools: liveness, LLM check, guidance recording, context reset, routing.

Split from ``general_tools.py`` — all ``@mcp_flowcept.tool()`` wrappers for session management
and the ``prompt_handler`` message router.
"""

import json
from typing import List

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.llm.builders import build_llm_model, normalize_message
from flowcept.agents.context_manager import mcp_flowcept
from flowcept.agents.prompts.base_prompts import ROUTING_PROMPT, SMALL_TALK_PROMPT
from flowcept.agents.mcp.mcp_tools.in_memory_task_query_mcp_tools import run_df_query
from flowcept.agents.mcp.mcp_tools.in_memory_workflow_query_mcp_tools import run_workflow_query
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


def _external_llm_enabled() -> bool:
    """Return True when agent is configured to use an external LLM orchestrator."""
    from flowcept.configs import AGENT

    return bool(AGENT.get("external_llm", False))


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


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def prompt_handler(message: str) -> ToolResult:
    """Route a user message by prefix or LLM classification.

    Prefix routing (no LLM call):
    - ``w:<query>`` → workflow query
    - ``t:<query>`` → task DataFrame query
    - ``o:<query>`` → object DataFrame query
    - ``save``, ``result = df``, ``df`` keywords → DataFrame query
    - ``reset context`` / ``@record`` / ``@show records`` / ``@reset records`` → session actions

    Falls back to LLM routing when no prefix matches.

    Parameters
    ----------
    message : str
        User's natural language input.

    Returns
    -------
    ToolResult
    """
    normalized_message = message.strip().lower()
    if normalized_message.startswith("w:"):
        query = message.split(":", 1)[1].strip()
        return run_workflow_query(query=query)
    if normalized_message.startswith("t:"):
        query = message.split(":", 1)[1].strip()
        return run_df_query(query=query, llm=None, plot=False, context_kind="tasks")
    if normalized_message.startswith("o:"):
        query = message.split(":", 1)[1].strip()
        return run_df_query(query=query, llm=None, plot=False, context_kind="objects")

    for key in ("df", "save", "result = df"):
        if key in message:
            return run_df_query(query=message, llm=None, plot=False)

    if "reset context" in message:
        return reset_context()
    if "@record" in message:
        return record_guidance(message)
    if "@show records" in message:
        return show_records()
    if "@reset records" in message:
        return reset_records()

    if _external_llm_enabled():
        return ToolResult(
            code=201,
            result=(
                "external_llm mode is enabled. Internal LLM routing is disabled. "
                "Use explicit commands such as 'save', 'result = df ...', "
                "'t: <task question>', 'o: <object question>', 'w: <workflow question>', "
                "'reset context', '@record', '@show records', or '@reset records'."
            ),
        )

    llm = build_llm_model()
    message = normalize_message(message)

    route = llm.invoke(ROUTING_PROMPT + message)

    if route == "small_talk":
        return ToolResult(code=201, result=llm.invoke(SMALL_TALK_PROMPT + message))
    elif route == "in_context_query":
        return run_df_query(message, llm=llm, plot=False)
    elif route == "plot":
        return run_df_query(message, llm=llm, plot=True)
    elif route in ("historical_prov_query", "in_chat_query"):
        return ToolResult(code=201, result=llm.invoke(SMALL_TALK_PROMPT + message))
    else:
        return ToolResult(code=404, result="I don't know how to route.")
