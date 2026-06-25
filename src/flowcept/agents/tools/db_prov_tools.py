"""MCP adapters exposing the shared provenance tool core to external agent clients.

Thin ``@mcp.tool`` wrappers around :mod:`flowcept.agents.tools.prov_tools`, giving MCP
clients (Claude Code, Codex, etc.) real DB-backed provenance querying — the same tool
core used by the webservice chat.
"""

from typing import Any, Dict, List, Optional

from flowcept.agents.agents_utils import ToolResult
from flowcept.agents.flowcept_ctx_manager import mcp_flowcept
from flowcept.agents.tools import prov_tools


@mcp_flowcept.tool()
def query_provenance_tasks(
    filter: Optional[Dict[str, Any]] = None,
    projection: Optional[List[str]] = None,
    limit: int = 100,
    sort: Optional[List[Dict[str, Any]]] = None,
) -> ToolResult:
    """Query task provenance records in the database with a Mongo-style filter."""
    return prov_tools.query_tasks(filter=filter, projection=projection, limit=limit, sort=sort)


@mcp_flowcept.tool()
def query_provenance_workflows(filter: Optional[Dict[str, Any]] = None, limit: int = 100) -> ToolResult:
    """Query workflow provenance records in the database with a Mongo-style filter."""
    return prov_tools.query_workflows(filter=filter, limit=limit)


@mcp_flowcept.tool()
def get_provenance_task_summary(filter: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Summarize tasks matching a filter: status counts, per-activity durations, time range."""
    return prov_tools.get_task_summary(filter=filter)


@mcp_flowcept.tool()
def list_provenance_campaigns() -> ToolResult:
    """List derived campaign summaries (campaigns group workflows and tasks)."""
    return prov_tools.list_campaigns()


@mcp_flowcept.tool()
def list_provenance_agents() -> ToolResult:
    """List derived agent summaries (agents observed in task provenance)."""
    return prov_tools.list_agents()
