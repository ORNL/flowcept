"""Dashboard agent tools: chart building and dashboard CRUD.

Plain Python — no LangChain, no MCP, no webservice imports.
These tools are used by the LangGraph chat agent and MCP server; framework
wrappers live in their respective layers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flowcept.agents.tool_result import ToolResult
from flowcept.commons.daos.docdb_dao.docdb_dao_utils import validate_filter as _validate_filter
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import normalize_docs
from flowcept.flowcept_api.db_api import DBAPI


def _guarded(tool_name: str):
    """Decorator: validate filters, cap limits, and convert errors to ToolResult codes."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                if "filter" in kwargs:
                    _validate_filter(kwargs.get("filter"))
                return func(*args, **kwargs)
            except ValueError as e:
                return ToolResult(code=400, result=str(e), tool_name=tool_name)
            except Exception as e:
                FlowceptLogger().exception(e)
                return ToolResult(code=499, result=f"Error in {tool_name}: {e}", tool_name=tool_name)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


def _normalize(docs: List[Dict]) -> List[Dict]:
    return normalize_docs(docs)


@_guarded("make_chart")
def make_chart(card_spec: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Build a chart card: resolve a declarative data binding into plottable rows.

    Parameters
    ----------
    card_spec : dict
        A dashboard chart spec with a ``data`` binding describing what to query.
    context : dict, optional
        Extra filter ANDed into the chart data filter (e.g., ``{"workflow_id": "..."}``).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"chart": <spec>, "rows": [...], "count": int}``.
    """
    data_spec = card_spec.get("data")
    if not data_spec:
        return ToolResult(code=400, result="Chart spec must include a data binding.", tool_name="make_chart")
    _validate_filter(data_spec.get("filter", {}))
    if context:
        _validate_filter(context)
    resolved = DBAPI().resolve_chart_data(data_spec, context=context)
    result = {"chart": card_spec, "rows": _normalize(resolved["rows"]), "count": resolved["count"]}
    return ToolResult(code=301, result=result, tool_name="make_chart")


@_guarded("get_dashboard")
def get_dashboard(dashboard_id: str) -> ToolResult:
    """Get a stored dashboard spec by id.

    Parameters
    ----------
    dashboard_id : str
        Dashboard identifier.

    Returns
    -------
    ToolResult
        ``result`` holds the dashboard spec dict, or a 404 message.
    """
    doc = DBAPI.get_dao_instance().get_dashboard(dashboard_id)
    if doc is None:
        return ToolResult(code=404, result=f"Dashboard not found: {dashboard_id}", tool_name="get_dashboard")
    return ToolResult(code=301, result=doc, tool_name="get_dashboard")


@_guarded("update_dashboard")
def update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> ToolResult:
    """Replace a stored dashboard spec, preserving id and creation time.

    Parameters
    ----------
    dashboard_id : str
        Dashboard identifier.
    spec : dict
        Full replacement dashboard spec.

    Returns
    -------
    ToolResult
        ``result`` holds the saved dashboard spec dict.
    """
    dao = DBAPI.get_dao_instance()
    existing = dao.get_dashboard(dashboard_id)
    if existing is None:
        return ToolResult(code=404, result=f"Dashboard not found: {dashboard_id}", tool_name="update_dashboard")
    _validate_filter(spec.get("context", {}))
    for card in spec.get("charts", []):
        if card.get("data"):
            _validate_filter(card["data"].get("filter", {}))
    spec["dashboard_id"] = dashboard_id
    spec["created_at"] = existing.get("created_at")
    spec["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not dao.save_dashboard(spec):
        return ToolResult(code=500, result="Could not save dashboard.", tool_name="update_dashboard")
    return ToolResult(code=301, result=spec, tool_name="update_dashboard")
