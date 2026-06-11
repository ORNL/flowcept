"""Shared provenance tool core.

Plain-Python functions over the provenance DB used by BOTH the webservice chat
(`/api/v1/chat`, via langchain tool wrappers) and the MCP agent (via ``@mcp.tool``
wrappers), so the two LLM surfaces never drift apart. All results follow the
``ToolResult`` convention. No web-framework imports here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from datetime import datetime, timezone

from flowcept.agents.agents_utils import ToolResult
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_CHAT_MAX_QUERY_LIMIT
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.schemas.dashboards import DashboardChart, DashboardSpec
from flowcept.webservice.services import stats
from flowcept.webservice.services.dashboard_store import get_dashboard_store
from flowcept.webservice.services.serializers import normalize_docs

ALLOWED_FILTER_OPERATORS = {
    "$and",
    "$or",
    "$nor",
    "$not",
    "$exists",
    "$eq",
    "$ne",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$in",
    "$nin",
    "$regex",
}

MAX_QUERY_LIMIT = AGENT_CHAT_MAX_QUERY_LIMIT


def validate_filter(filter_doc: Optional[Dict[str, Any]]) -> None:
    """Validate a Mongo-style filter against the safe-operator allowlist.

    Raises
    ------
    ValueError
        When the filter uses an operator outside the allowlist or has a bad shape.
    """

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.startswith("$"):
                    if key not in ALLOWED_FILTER_OPERATORS:
                        raise ValueError(f"Unsupported filter operator: {key}")
                    if key in {"$and", "$or", "$nor"} and not isinstance(item, list):
                        raise ValueError(f"{key} must be a list.")
                _walk(item)
        elif isinstance(value, list):
            for item in value:
                _walk(item)

    _walk(filter_doc or {})


def _guarded(tool_name: str):
    """Decorator: validate filters, cap limits, and convert errors to ToolResult codes."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                if "filter" in kwargs:
                    validate_filter(kwargs.get("filter"))
                if "limit" in kwargs and kwargs["limit"]:
                    kwargs["limit"] = min(int(kwargs["limit"]), MAX_QUERY_LIMIT)
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


@_guarded("query_tasks")
def query_tasks(
    filter: Optional[Dict[str, Any]] = None,
    projection: Optional[List[str]] = None,
    limit: int = 100,
    sort: Optional[List[Dict[str, Any]]] = None,
) -> ToolResult:
    """Query task provenance records with a Mongo-style filter.

    Parameters
    ----------
    filter : dict, optional
        Mongo-style filter (e.g., ``{"workflow_id": "...", "status": "ERROR"}``).
    projection : list of str, optional
        Fields to include in results.
    limit : int, optional
        Maximum records (capped by settings).
    sort : list of dict, optional
        ``[{"field": "started_at", "order": -1}]``.

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    sort_tuples = None if not sort else [(s["field"], s["order"]) for s in sort]
    docs = DBAPI().task_query(filter=filter or {}, projection=projection, limit=limit, sort=sort_tuples) or []
    items = _normalize(docs)
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="query_tasks")


@_guarded("query_workflows")
def query_workflows(filter: Optional[Dict[str, Any]] = None, limit: int = 100) -> ToolResult:
    """Query workflow provenance records with a Mongo-style filter.

    Parameters
    ----------
    filter : dict, optional
        Mongo-style filter (e.g., ``{"campaign_id": "..."}``).
    limit : int, optional
        Maximum records (capped by settings).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    docs = (DBAPI().workflow_query(filter=filter or {}) or [])[:limit]
    items = _normalize(docs)
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="query_workflows")


@_guarded("get_task_summary")
def get_task_summary(filter: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Summarize tasks matching a filter: status counts, per-activity durations, time range.

    Parameters
    ----------
    filter : dict, optional
        Mongo-style filter over tasks.

    Returns
    -------
    ToolResult
        ``result`` holds the summary dict.
    """
    summary = stats.task_summary(DBAPI(), filter or {})
    return ToolResult(code=301, result=_normalize([summary])[0], tool_name="get_task_summary")


@_guarded("list_campaigns")
def list_campaigns() -> ToolResult:
    """List derived campaign summaries (campaigns group workflows and tasks).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    items = _normalize(stats.derive_campaigns(DBAPI()))
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="list_campaigns")


@_guarded("list_agents")
def list_agents() -> ToolResult:
    """List derived agent summaries (agents observed in task provenance).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    items = _normalize(stats.derive_agents(DBAPI()))
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="list_agents")


@_guarded("make_chart")
def make_chart(card_spec: Dict[str, Any], context: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Build a dashboard-style chart card: validate the spec and resolve its data rows.

    Parameters
    ----------
    card_spec : dict
        A dashboard ``DashboardChart`` spec (type chart/metric/table with a ``data`` binding).
    context : dict, optional
        Extra filter ANDed into the chart data filter (e.g., ``{"workflow_id": "..."}``).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"chart": <validated spec>, "rows": [...], "count": int}``.
    """
    card = DashboardChart(**card_spec)
    if card.data is None:
        return ToolResult(code=400, result="Chart spec must include a data binding.", tool_name="make_chart")
    validate_filter(card.data.filter)
    if context:
        validate_filter(context)
    resolved = stats.resolve_chart_data(DBAPI(), card.data, context=context)
    result = {"chart": card.model_dump(), "rows": _normalize(resolved["rows"]), "count": resolved["count"]}
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
    doc = get_dashboard_store().get(dashboard_id)
    if doc is None:
        return ToolResult(code=404, result=f"Dashboard not found: {dashboard_id}", tool_name="get_dashboard")
    return ToolResult(code=301, result=doc, tool_name="get_dashboard")


@_guarded("update_dashboard")
def update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> ToolResult:
    """Replace a stored dashboard spec (validated), preserving id and creation time.

    Parameters
    ----------
    dashboard_id : str
        Dashboard identifier.
    spec : dict
        Full replacement ``DashboardSpec``.

    Returns
    -------
    ToolResult
        ``result`` holds the saved dashboard spec dict.
    """
    store = get_dashboard_store()
    existing = store.get(dashboard_id)
    if existing is None:
        return ToolResult(code=404, result=f"Dashboard not found: {dashboard_id}", tool_name="update_dashboard")
    validated = DashboardSpec(**spec)
    validate_filter(validated.context)
    for card in validated.cards:
        if card.data is not None:
            validate_filter(card.data.filter)
    validated.dashboard_id = dashboard_id
    validated.created_at = existing.get("created_at")
    validated.updated_at = datetime.now(timezone.utc).isoformat()
    doc = validated.model_dump()
    if not store.save(doc):
        return ToolResult(code=500, result="Could not save dashboard.", tool_name="update_dashboard")
    return ToolResult(code=301, result=doc, tool_name="update_dashboard")
