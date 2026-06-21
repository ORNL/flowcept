"""Thin MCP wrappers for dashboard agent tools."""

from typing import Any, Dict, Optional

from flowcept.agents.data_query_tools import dashboard_tools
from flowcept.agents.mcp.context_manager import mcp_flowcept
from flowcept.agents.tool_result import ToolResult
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def make_chart(card_spec: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Build a chart from a declarative dashboard card spec."""
    return dashboard_tools.make_chart(card_spec=card_spec, context=context)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def get_dashboard(dashboard_id: str) -> ToolResult:
    """Get a stored dashboard spec by id."""
    return dashboard_tools.get_dashboard(dashboard_id=dashboard_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> ToolResult:
    """Replace a stored dashboard spec with a complete revised spec."""
    return dashboard_tools.update_dashboard(dashboard_id=dashboard_id, spec=spec)
