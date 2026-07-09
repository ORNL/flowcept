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
from flowcept.commons.daos.docdb_dao.docdb_dao_utils import validate_filter

MAX_QUERY_LIMIT = AGENT_CHAT_MAX_QUERY_LIMIT


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


def _normalize(docs: List[Dict]) -> List[Dict]:
    return normalize_docs(docs)


def _normalize_workflows(docs: List[Dict]) -> List[Dict]:
    """Normalize workflow docs, stripping heavy infrastructure-only fields for LLM responses."""
    pruned = [{k: v for k, v in doc.items() if k not in _WORKFLOW_HEAVY_FIELDS} for doc in docs]
    return normalize_docs(pruned)


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
    items = _normalize_workflows(docs)
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
    activity_stats = summary.get("activity_stats") or []
    summary["activity_ids"] = [row.get("activity_id") for row in activity_stats if row.get("activity_id")]
    summary["activity_counts"] = {
        row.get("activity_id"): row.get("count") for row in activity_stats if row.get("activity_id")
    }
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


@_guarded("query_objects")
def query_objects(
    filter: Optional[Dict[str, Any]] = None,
    projection: Optional[List[str]] = None,
    limit: int = 100,
) -> ToolResult:
    """Query stored data-object provenance records with a Mongo-style filter.

    Data objects include ML models (``object_type="ml_model"``), datasets
    (``object_type="dataset"``), and generic blobs.  Their ``custom_metadata``
    field carries artifact-specific information such as ``model_profile.params``,
    ``n_input_neurons``, ``loss``, ``split_ratio``, and ``n_samples``.
    Use this tool when the user asks about model parameters, dataset size, file
    types, artifact sizes, or any stored artifact metadata.

    Parameters
    ----------
    filter : dict, optional
        Mongo-style filter.  Common fields: ``object_type``, ``workflow_id``,
        ``task_id``, ``tags``.  ``custom_metadata`` sub-fields use dot-notation,
        e.g. ``{"custom_metadata.model_profile.params": {"$gt": 2}}``.
    projection : list of str, optional
        Fields to include (dot-notation accepted).
    limit : int, optional
        Maximum records (capped by settings).

    Returns
    -------
    ToolResult
        ``result`` holds ``{"items": [...], "count": int}``.
    """
    capped = min(limit, MAX_QUERY_LIMIT)
    docs = (DBAPI().blob_object_query(filter=filter or {}) or [])[:capped]
    items = _normalize(docs)
    if projection:
        safe_proj = set(_sanitize_projection(projection) or [])
        if safe_proj:
            items = [{k: v for k, v in d.items() if k in safe_proj} for d in items]
    return ToolResult(code=301, result={"items": items, "count": len(items)}, tool_name="query_objects")


@_guarded("highlight_lineage")
def highlight_lineage(  # noqa: E302
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


def fix_query(llm, query_params: Dict[str, Any], error: str) -> ToolResult:
    """Repair bad DB query parameters (filter/projection/sort) that caused a runtime error.

    Parameters
    ----------
    llm : callable
        LLM callable.
    query_params : dict
        The original query parameters dict (keys: filter, projection, sort, limit).
    error : str
        The error message produced when the query was attempted.

    Returns
    -------
    ToolResult
        ``result`` holds corrected ``query_params`` dict on success.
    """
    import json as _json
    from flowcept.agents.prompts.db_query_prompts import build_fix_query_prompt

    prompt = build_fix_query_prompt(query_params=query_params, error=error)
    try:
        response = llm.invoke(prompt)
        text = response.content if hasattr(response, "content") else str(response)
        corrected = _json.loads(text)
        return ToolResult(code=201, result=corrected, tool_name="fix_query")
    except Exception as e:
        return ToolResult(code=499, result=str(e), tool_name="fix_query")


class DBQueryTools:
    """DB-backed query path implementation of BaseQueryTools.

    Delegates to the module-level functions in this module, which are also
    used directly by the MCP and webservice layers.
    """

    def query_tasks(self, structured_arg: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Query tasks with a Mongo-style filter dict."""
        return query_tasks(filter=structured_arg)

    def query_objects(self, structured_arg: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Query objects with a Mongo-style filter dict."""
        return query_objects(filter=structured_arg)

    def query_workflows(self, structured_arg: Optional[Dict[str, Any]] = None) -> ToolResult:
        """Query workflows with a Mongo-style filter dict."""
        return query_workflows(filter=structured_arg)

    def generate_plot(self, structured_arg: Any) -> ToolResult:
        """Generate a chart from a declarative card_spec dict (DB path)."""
        from flowcept.agents.data_query_tools.dashboard_tools import make_chart

        return make_chart(card_spec=structured_arg)

    def get_schema_context(self) -> str:
        """Return workflow-scoped DB schema context string."""
        from flowcept.agents.prompts.db_query_prompts import build_db_schema_context

        return build_db_schema_context()

    def build_query_prompt(self, query: str, schema: str = None) -> str:
        """Build a Mongo filter-generation prompt for external LLM orchestration."""
        from flowcept.agents.prompts.db_query_prompts import build_db_schema_context

        schema_ctx = schema or build_db_schema_context()
        return f"{schema_ctx}\n\nUser query:\n{query}"

    def list_agents(self, filter: Optional[Dict] = None) -> ToolResult:
        """List derived agent summaries."""
        return list_agents(filter=filter)

    def list_campaigns(self, campaign_id: Optional[str] = None) -> ToolResult:
        """List derived campaign summaries."""
        return list_campaigns(campaign_id=campaign_id)
