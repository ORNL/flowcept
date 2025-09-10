import json

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

    llm = build_llm_model()

    prompt = ROUTING_PROMPT + message
    route = llm.invoke(prompt)

    if route == "small_talk":
        prompt = SMALL_TALK_PROMPT + message
        response = llm.invoke(prompt)
        return ToolResult(code=201, result=response)
    elif route == "plot":
        return run_df_query(llm, message, plot=True)
    elif route == "historical_prov_query":
        return ToolResult(code=201, result="We need to query the Provenance Database. Feature coming soon.")
    elif route == "in_context_query":
        return run_df_query(llm, message, plot=False)
    elif route == "in_chat_query":
        prompt = SMALL_TALK_PROMPT + message
        response = llm.invoke(prompt)
        return ToolResult(code=201, result=response)
    else:
        return ToolResult(code=404, result="I don't know how to route.")
