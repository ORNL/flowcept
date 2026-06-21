"""Shared provenance tool core.

Plain-Python functions over the provenance DB used by BOTH the webservice chat
(`/api/v1/chat`, via langchain tool wrappers) and the MCP agent (via ``@mcp.tool``
wrappers), so the two LLM surfaces never drift apart. All results follow the
``ToolResult`` convention. No web-framework imports here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.data_query_tools.tools_utils import query_runtime_retry
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_CHAT_MAX_QUERY_LIMIT
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.commons.utils import normalize_docs

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


def _sanitize_projection(projection: Optional[List[str]]) -> Optional[List[str]]:
    """Remove child paths whose parent field is already in *projection*.

    MongoDB raises ``OperationFailure: Path collision`` when a projection
    includes both ``"generated"`` and ``"generated.val_accuracy"``.  This
    helper strips the redundant children so the parent field covers them.
    """
    if not projection:
        return projection
    result = []
    for field in projection:
        parts = field.split(".")
        # keep this field only if none of its parent paths is already included
        parent_already_included = any(".".join(parts[:i]) in projection for i in range(1, len(parts)))
        if not parent_already_included:
            result.append(field)
    return result or None


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
    proj_holder = [_sanitize_projection(projection)]

    def _execute():
        return (
            DBAPI().task_query(
                filter=filter or {},
                projection=proj_holder[0],
                limit=limit,
                sort=sort_tuples,
            )
            or []
        )

    def _fix(exc, attempt):
        # Only auto-fix MongoDB projection path-collision errors; let others propagate.
        if "Path collision" not in str(exc):
            raise exc
        proj_holder[0] = _sanitize_projection(proj_holder[0])
        return _execute

    docs = query_runtime_retry(_execute, _fix, max_attempts=2)
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
    summary = DBAPI().task_summary(filter or {})
    return ToolResult(code=301, result=_normalize([summary])[0], tool_name="get_task_summary")


@_guarded("list_campaigns")
def list_campaigns(campaign_id: Optional[str] = None) -> ToolResult:
    """List derived campaign summaries (campaigns group workflows and tasks).

    Parameters
    ----------
    campaign_id : str, optional
        When provided, only the summary for that campaign is returned.
        Pass the campaign_id from the user context to scope the result.

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    items = _normalize(DBAPI().derive_campaigns(campaign_id=campaign_id))
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="list_campaigns")


@_guarded("list_agents")
def list_agents(filter: Dict = None) -> ToolResult:
    """List derived agent summaries (agents observed in task provenance).

    Parameters
    ----------
    filter : dict, optional
        Mongo-style filter to scope the agent derivation (e.g., ``{"workflow_id": "..."}``).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    items = _normalize(DBAPI().derive_agents(filter))
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="list_agents")


@_guarded("highlight_lineage")
def highlight_lineage(
    task_ids: Optional[List[str]] = None,
    filter: Optional[Dict[str, Any]] = None,
    workflow_id: Optional[str] = None,
) -> ToolResult:
    """Highlight the full provenance lineage of tasks in the Dataflow graph.

    Accepts either explicit ``task_ids`` or a Mongo-style ``filter`` to locate
    the tasks of interest. ``workflow_id`` scopes the lineage traversal to one
    workflow execution. The result is forwarded to the UI, which visually
    highlights the ancestor/descendant chain in the Dataflow tab.

    Parameters
    ----------
    task_ids : list of str, optional
        Explicit task IDs to highlight.
    filter : dict, optional
        Mongo-style filter to find the seed tasks when ``task_ids`` is omitted.
    workflow_id : str, optional
        Workflow execution id — required for lineage traversal.

    Returns
    -------
    ToolResult
        ``result`` holds ``{"task_ids": [...], "seed_count": int}``.
    """
    db = DBAPI()
    resolved_ids = list(task_ids or [])

    if not resolved_ids and filter is not None:
        scoped = dict(filter)
        if workflow_id:
            scoped["workflow_id"] = workflow_id
        docs = db.task_query(filter=scoped, projection=["task_id"], limit=100) or []
        resolved_ids = [d["task_id"] for d in docs if d.get("task_id")]

    if not resolved_ids:
        return ToolResult(code=404, result="No tasks found for the given criteria.", tool_name="highlight_lineage")

    # Fetch activity names for the resolved task IDs so the LLM can describe the lineage.
    activity_map: Dict[str, str] = {}
    try:
        detail_docs = (
            db.task_query(
                filter={"task_id": {"$in": resolved_ids}},
                projection=["task_id", "activity_id", "agent_id"],
                limit=len(resolved_ids) + 10,
            )
            or []
        )
        for doc in detail_docs:
            tid = doc.get("task_id", "")
            if tid:
                activity_map[tid] = doc.get("activity_id") or doc.get("agent_id") or ""
    except Exception:
        pass

    # Return seed task IDs. The frontend BFS expands ancestors/descendants
    # from these seeds using the dataflow graph — a single source of truth for lineage.
    return ToolResult(
        code=301,
        result={"task_ids": resolved_ids, "activities": activity_map},
        tool_name="highlight_lineage",
    )
