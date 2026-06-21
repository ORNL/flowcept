"""Thin MCP wrappers for DF (DataFrame) query tools.

One-liner delegates to :mod:`flowcept.agents.data_query_tools.df_query_tools`.
MCP context lookup (df, schema, value_examples, custom_user_guidance) happens here.
"""

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.mcp.context_manager import mcp_flowcept, get_df_context, ctx_manager, EMPTY_DF_MESSAGE
from flowcept.agents.data_query_tools import df_query_tools as _core
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task

_WORKFLOW_HEAVY_FIELDS = frozenset(
    {
        "machine_info",
        "flowcept_settings",
        "code_repository",
        "conf",
        "extra_metadata",
        "environment_id",
        "sys_name",
        "interceptor_ids",
        "adapter_id",
        "flowcept_version",
    }
)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def get_workflow_context() -> ToolResult:
    """Return the in-memory workflow record(s) currently loaded in the agent context.

    The DF path stores workflow provenance in the MCP context rather than in the
    tasks DataFrame.  This tool is the DF-path counterpart to the DB-path
    ``query_workflows`` tool: both return ``{items, count}`` with heavy
    infrastructure fields stripped.

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    wf = ctx_manager.context.workflow_msg_obj
    if not wf:
        return ToolResult(code=404, result="No workflow loaded in agent context.", tool_name="get_workflow_context")
    pruned = {k: v for k, v in wf.items() if k not in _WORKFLOW_HEAVY_FIELDS}
    return ToolResult(code=301, result={"items": [pruned], "count": 1}, tool_name="get_workflow_context")


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
