"""LangChain tool wrappers built from MCP tools for the chat orchestrator.

One function per logical tool.  ``tool_context`` (``"db"`` or ``"df"``) is bound
at build time and is never exposed to the LLM.
Mode-divergent tools use a union signature: ``query_params`` for DB,
``code`` for DF; the function body routes internally.
All MCP tool names are taken from ``function.__name__`` — no raw strings.
"""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import create_model

from flowcept.agents.mcp.mcp_client import run_tool
from flowcept.agents.mcp.mcp_tools import db_query_mcp_tools as _db
from flowcept.agents.mcp.mcp_tools import df_query_mcp_tools as _df
from flowcept.agents.mcp.mcp_tools import dashboard_mcp_tools as _dash


def _run_mcp(tool_name: str, **kwargs) -> str:
    """Call an MCP tool by name and return the serialized response."""
    return run_tool(tool_name, kwargs=kwargs)[0]


def _scoped_filter(context: Optional[Dict[str, Any]], filter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    scoped = dict(filter or {})
    for key in ("workflow_id", "campaign_id"):
        if (context or {}).get(key):
            scoped[key] = context[key]
    return scoped


def _coerce_projection(p: Any) -> Optional[List[str]]:
    if p is None:
        return None
    if isinstance(p, dict):
        return [k for k, v in p.items() if v]
    return list(p)


def _coerce_sort(s: Any) -> Optional[List[Dict[str, Any]]]:
    if s is None:
        return None
    if isinstance(s, dict):
        return [{"field": k, "order": v} for k, v in s.items()]
    return list(s)


# ---------------------------------------------------------------------------
# Logical tools — one def each, tool_context bound via partial
# ---------------------------------------------------------------------------


def query_tasks(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    query_params: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
) -> str:
    """Query task provenance records.

    DB mode: pass ``query_params`` with keys ``filter``, ``projection``, ``limit``, ``sort``.
    DF mode: pass ``code`` — pandas code assigned to ``result`` querying the tasks DataFrame.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_query_tasks.__name__, code=code)
    p = query_params or {}
    return _run_mcp(
        _db.db_query_tasks.__name__,
        filter=_scoped_filter(context, p.get("filter")),
        projection=_coerce_projection(p.get("projection")),
        limit=p.get("limit", 100),
        sort=_coerce_sort(p.get("sort")),
    )


def query_workflows(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    query_params: Optional[Dict[str, Any]] = None,
) -> str:
    """Query workflow provenance records.

    DB mode: pass ``query_params`` with keys ``filter``, ``limit``.
    DF mode: returns the workflow record loaded in the agent's in-memory context.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_query_workflows.__name__)
    p = query_params or {}
    return _run_mcp(
        _db.db_query_workflows.__name__,
        filter=_scoped_filter(context, p.get("filter")),
        limit=p.get("limit", 100),
    )


def query_objects(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    query_params: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
) -> str:
    """Query stored data-object records (ML models, datasets, blobs).

    DB mode: pass ``query_params`` with keys ``filter``, ``projection``, ``limit``.
    DF mode: pass ``code`` — pandas code querying the objects DataFrame.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_query_objects.__name__, code=code)
    p = query_params or {}
    obj_filter = dict(p.get("filter") or {})
    if (context or {}).get("workflow_id"):
        obj_filter["workflow_id"] = context["workflow_id"]
    return _run_mcp(
        _db.db_query_objects.__name__,
        filter=obj_filter,
        projection=_coerce_projection(p.get("projection")),
        limit=p.get("limit", 100),
    )


def get_task_summary(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    query_params: Optional[Dict[str, Any]] = None,
) -> str:
    """Summarize tasks: status counts, per-activity durations, time range.

    DB mode: pass ``query_params`` with key ``filter``.
    DF mode: no parameters needed; operates on the loaded in-memory DataFrame.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_get_task_summary.__name__)
    p = query_params or {}
    return _run_mcp(_db.db_get_task_summary.__name__, filter=_scoped_filter(context, p.get("filter")))


def list_campaigns(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    campaign_id: Optional[str] = None,
) -> str:
    """List derived campaign summaries (campaigns group workflows and tasks).

    DB mode: optionally pass ``campaign_id`` to scope to one campaign.
    DF mode: derives campaign summaries from the in-memory tasks DataFrame.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_list_campaigns.__name__)
    effective_id = campaign_id or (context or {}).get("campaign_id")
    return _run_mcp(_db.db_list_campaigns.__name__, campaign_id=effective_id)


def list_agents(
    tool_context: str,
    context: Optional[Dict[str, Any]],
) -> str:
    """List derived agent summaries observed in task provenance.

    Both paths scope automatically to the current workflow when available.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_list_agents.__name__)
    workflow_id = (context or {}).get("workflow_id")
    effective_filter = {"workflow_id": workflow_id} if workflow_id else None
    return _run_mcp(_db.db_list_agents.__name__, filter=effective_filter)


def make_chart(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    query_params: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
) -> str:
    """Build a chart for the UI.

    DB mode: pass ``query_params`` containing a declarative ``card_spec`` dict.
    DF mode: pass ``code`` (pandas code producing the chart data) and optionally
             include ``plot_code`` inside ``query_params``.
    """
    if tool_context == "df":
        p = query_params or {}
        return _run_mcp(_dash.df_make_chart.__name__, result_code=code or "", plot_code=p.get("plot_code", ""))
    p = query_params or {}
    card_spec = dict(p.get("card_spec") or p)
    data_spec = dict(card_spec.get("data") or {})
    data_spec["filter"] = _scoped_filter(context, data_spec.get("filter"))
    card_spec["data"] = data_spec
    return _run_mcp(_dash.db_make_chart.__name__, card_spec=card_spec, context=None)


def highlight_lineage(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    task_ids: Optional[Any] = None,
    query_params: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
) -> str:
    """Highlight the full provenance lineage of tasks in the Dataflow graph.

    DB mode: pass ``task_ids`` (list or single string) or ``query_params`` with ``filter``.
    DF mode: pass ``task_ids`` directly, or ``code`` to select seed tasks from the DataFrame.
    """
    if tool_context == "df":
        ids = [task_ids] if isinstance(task_ids, str) else list(task_ids or [])
        return _run_mcp(_df.df_highlight_lineage.__name__, task_ids=ids or None, code=code)
    wf_id = (context or {}).get("workflow_id")
    ids = [task_ids] if isinstance(task_ids, str) else list(task_ids or [])
    p = query_params or {}
    return _run_mcp(
        _db.db_highlight_lineage.__name__,
        task_ids=ids or None,
        filter=p.get("filter"),
        workflow_id=wf_id,
    )


def fix_query(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    query_params: Optional[Dict[str, Any]] = None,
    code: Optional[str] = None,
    error: Optional[str] = None,
) -> str:
    """Repair a failed query.

    DB mode: pass ``query_params`` (the bad filter/projection/sort) and ``error``.
    DF mode: pass ``code`` (the bad pandas code) and optionally ``error``.
    """
    if tool_context == "df":
        return _run_mcp(_df.df_fix_query.__name__, raw_text=code or "", runtime_error=error)
    return _run_mcp(_db.db_fix_query.__name__, query_params=query_params or {}, error=error or "")


def get_dashboard(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    dashboard_id: str = "",
) -> str:
    """Get a stored dashboard spec by id."""
    if tool_context == "df":
        return _run_mcp(_dash.df_get_dashboard.__name__, dashboard_id=dashboard_id)
    return _run_mcp(_dash.db_get_dashboard.__name__, dashboard_id=dashboard_id)


def update_dashboard(
    tool_context: str,
    context: Optional[Dict[str, Any]],
    dashboard_id: str = "",
    spec: Optional[Dict[str, Any]] = None,
) -> str:
    """Replace a stored dashboard spec with a complete revised spec."""
    if tool_context == "df":
        return _run_mcp(_dash.df_update_dashboard.__name__, dashboard_id=dashboard_id, spec=spec or {})
    return _run_mcp(_dash.db_update_dashboard.__name__, dashboard_id=dashboard_id, spec=spec or {})


# ---------------------------------------------------------------------------
# LangChain tool builder
# ---------------------------------------------------------------------------


def _format_error(exc: BaseException, _depth: int = 0) -> str:
    """Return a user-facing error string, unwrapping ExceptionGroup to its real cause."""
    if _depth > 5:
        return str(exc) or type(exc).__name__
    if hasattr(exc, "exceptions"):
        inner = "; ".join(_format_error(sub, _depth + 1) for sub in exc.exceptions)
        return (
            f"A tool call failed ({inner}). "
            "This may be a transient service error — try rephrasing your question "
            "or narrowing the scope (e.g. add a workflow_id or campaign_id)."
        )
    if exc.__cause__ is not None:
        return _format_error(exc.__cause__, _depth + 1)
    return str(exc) or type(exc).__name__


# Parameters hidden from the LLM per mode to prevent ambiguity in the union signature.
# DB mode exposes query_params; DF mode exposes code.  Hiding the irrelevant parameter
# prevents the LLM from omitting required arguments when both are Optional.
_DB_HIDDEN_PARAMS = frozenset({"code"})
_DF_HIDDEN_PARAMS = frozenset({"query_params"})


def _make_tool(fn, tool_context: str, context: Optional[Dict[str, Any]]) -> StructuredTool:
    """Build a LangChain StructuredTool with tool_context and context bound.

    Uses an explicit pydantic schema derived from *fn*'s signature (skipping the
    first two bound params) so that LangChain's schema inference never sees a
    ``functools.partial`` object (which ``get_type_hints`` cannot inspect).
    Mode-irrelevant parameters (``code`` in DB mode, ``query_params`` in DF mode)
    are excluded from the schema so the LLM receives an unambiguous interface.
    """
    hidden = _DB_HIDDEN_PARAMS if tool_context == "db" else _DF_HIDDEN_PARAMS
    # Skip tool_context and context — they are bound at build time.
    sig = inspect.signature(fn)
    user_params = [p for p in list(sig.parameters.values())[2:] if p.name not in hidden]
    field_defs: Dict[str, Any] = {}
    for p in user_params:
        ann = p.annotation if p.annotation is not inspect.Parameter.empty else Any
        default = p.default if p.default is not inspect.Parameter.empty else ...
        field_defs[p.name] = (ann, default)
    schema = create_model(f"{fn.__name__}_schema", **field_defs)

    def _run(**kwargs):
        return fn(tool_context, context, **kwargs)

    return StructuredTool(
        name=fn.__name__,
        description=fn.__doc__ or "",
        args_schema=schema,
        func=_run,
    )


_ALL_TOOLS = [
    query_tasks,
    query_workflows,
    query_objects,
    get_task_summary,
    list_campaigns,
    list_agents,
    make_chart,
    highlight_lineage,
    fix_query,
]

_DASHBOARD_TOOLS = [get_dashboard, update_dashboard]


def build_langchain_tools(
    context: Optional[Dict[str, Any]], allow_dashboard_edit: bool
) -> List[StructuredTool]:
    """Wrap all logical tools as LangChain StructuredTools scoped to *context*.

    The same tool set is used for both DB and DF modes; ``tool_context`` is
    bound via ``partial`` and never exposed to the LLM.
    """
    tool_context = (context or {}).get("tool_context", "db")
    tools = [_make_tool(fn, tool_context, context) for fn in _ALL_TOOLS]
    if allow_dashboard_edit:
        tools += [_make_tool(fn, tool_context, context) for fn in _DASHBOARD_TOOLS]
    return tools


# Backward-compatible alias so chat_orchestrator_service.py needs no immediate change.
_build_langchain_tools = build_langchain_tools
