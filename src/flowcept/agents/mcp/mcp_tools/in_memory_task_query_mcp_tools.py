"""Thin MCP wrappers for in-memory task DataFrame query tools.

One-liner delegates to :mod:`flowcept.agents.data_query_tools.in_memory_task_query_tools`.
MCP context lookup (df, schema, value_examples, custom_user_guidance) happens here.
"""

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.mcp.context_manager import mcp_flowcept, get_df_context, EMPTY_DF_MESSAGE
from flowcept.agents.data_query_tools import in_memory_task_query_tools as _core
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def run_df_query(query: str, llm=None, plot: bool = False, context_kind: str = "tasks") -> ToolResult:
    r"""Run a natural language query against the current context DataFrame.

    This tool retrieves the active DataFrame, schema, and example values
    from the MCP Flowcept context and uses an LLM to process the query.

    Parameters
    ----------
    query : str
        Natural language query or Python code snippet.
    llm : callable, optional
        LLM callable. Built from settings if None.
    plot : bool, optional
        If True, generate plotting code.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    ToolResult
    """
    df, schema, value_examples, custom_user_guidance = get_df_context(context_kind=context_kind)
    return _core.run_df_query(
        query=query,
        df=df,
        schema=schema,
        value_examples=value_examples,
        custom_user_guidance=custom_user_guidance,
        llm=llm,
        plot=plot,
        context_kind=context_kind,
    )


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def execute_generated_df_code(user_code: str, context_kind: str = "tasks") -> ToolResult:
    """Execute externally generated pandas code against the current agent DataFrame.

    Parameters
    ----------
    user_code : str
        Pandas code expected to assign output to ``result``.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    ToolResult
    """
    df, _, _, _ = get_df_context(context_kind=context_kind)
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE)
    return _core.execute_df_code(user_code=user_code, df=df)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def extract_or_fix_python_code(raw_text: str, runtime_error: str = None, context_kind: str = "tasks") -> ToolResult:
    """Extract or repair pandas code using the current agent DataFrame columns."""
    from flowcept.agents.llm.builders import build_llm_model

    df, _, _, _ = get_df_context(context_kind=context_kind)
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE)
    return _core.extract_or_fix_python_code(
        build_llm_model(track_tools=False),
        raw_text,
        list(df.columns),
        runtime_error=runtime_error,
    )
