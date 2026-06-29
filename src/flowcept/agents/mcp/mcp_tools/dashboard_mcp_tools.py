"""Thin MCP wrappers for dashboard agent tools — DB and DF paths."""

from typing import Any, Dict, Optional

from flowcept.agents.data_query_tools import dashboard_tools
from flowcept.agents.mcp.context_manager import mcp_flowcept, get_df_context, EMPTY_DF_MESSAGE
from flowcept.agents.tool_result import ToolResult
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


# ---------------------------------------------------------------------------
# DB path
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_make_chart(card_spec: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Build a chart from a declarative dashboard card spec; the UI renders the result."""
    return dashboard_tools.make_chart(card_spec=card_spec, context=context)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_get_dashboard(dashboard_id: str) -> ToolResult:
    """Get a stored dashboard spec by id."""
    return dashboard_tools.get_dashboard(dashboard_id=dashboard_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> ToolResult:
    """Replace a stored dashboard spec with a complete revised spec."""
    return dashboard_tools.update_dashboard(dashboard_id=dashboard_id, spec=spec)


# ---------------------------------------------------------------------------
# DF path
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_make_chart(result_code: str, plot_code: str = "") -> ToolResult:
    """Generate a chart from the in-memory tasks DataFrame.

    result_code: pandas code (assigned to ``result``) producing the data for plotting.
    plot_code: matplotlib/plotly code to render the chart (may reference ``result``).
    """
    from flowcept.agents.data_query_tools.df_query_tools import execute_df_code

    df, _, _, _ = get_df_context(context_kind="tasks")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_make_chart")
    result = execute_df_code(user_code=result_code, df=df)
    if not plot_code or result.code >= 400:
        return result
    r = result.result if isinstance(result.result, dict) else {}
    r["plot_code"] = plot_code
    return ToolResult(code=result.code, result=r, tool_name="df_make_chart")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_get_dashboard(dashboard_id: str) -> ToolResult:
    """Get a stored dashboard spec by id (DF path — delegates to the same dashboard store)."""
    return dashboard_tools.get_dashboard(dashboard_id=dashboard_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> ToolResult:
    """Replace a stored dashboard spec with a complete revised spec (DF path)."""
    return dashboard_tools.update_dashboard(dashboard_id=dashboard_id, spec=spec)
