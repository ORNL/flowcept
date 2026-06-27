"""LangChain tool wrappers built from MCP tools for the chat orchestrator."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flowcept.agents.mcp.mcp_client import run_tool

# MCP tool registration names — import these in prompt builders so renames fail loudly.
DF_QUERY_TOOL = "generate_result_df"
OBJECTS_QUERY_TOOL = "generate_objects_df"
QUERY_TASKS_TOOL = "query_tasks"
QUERY_WORKFLOWS_TOOL = "query_workflows"
GET_TASK_SUMMARY_TOOL = "get_task_summary"
LIST_CAMPAIGNS_TOOL = "list_campaigns"
LIST_AGENTS_TOOL = "list_agents"
MAKE_CHART_TOOL = "make_chart"
HIGHLIGHT_LINEAGE_TOOL = "highlight_lineage"
GET_DASHBOARD_TOOL = "get_dashboard"
UPDATE_DASHBOARD_TOOL = "update_dashboard"


def _format_error(exc: BaseException, _depth: int = 0) -> str:
    """Return a user-facing error string, unwrapping ExceptionGroup to its real cause."""
    if _depth > 5:
        return str(exc) or type(exc).__name__
    if hasattr(exc, "exceptions"):  # ExceptionGroup / BaseExceptionGroup (Python 3.11+)
        inner = "; ".join(_format_error(sub, _depth + 1) for sub in exc.exceptions)
        return (
            f"A tool call failed ({inner}). "
            "This may be a transient service error — try rephrasing your question "
            "or narrowing the scope (e.g. add a workflow_id or campaign_id)."
        )
    if exc.__cause__ is not None:
        return _format_error(exc.__cause__, _depth + 1)
    return str(exc) or type(exc).__name__


def _build_langchain_tools(context: Optional[Dict[str, Any]], allow_dashboard_edit: bool):
    """Wrap MCP tools as LangChain tools scoped to *context*."""
    from langchain_core.tools import tool

    def _run_mcp(tool_name: str, **kwargs) -> str:
        return run_tool(tool_name, kwargs=kwargs)[0]

    def _coerce_projection(p: Any) -> Optional[List[str]]:
        """Accept a list of field names or a Mongo projection dict {field: 1}."""
        if p is None:
            return None
        if isinstance(p, dict):
            return [k for k, v in p.items() if v]
        return list(p)

    def _coerce_sort(s: Any) -> Optional[List[Dict[str, Any]]]:
        """Accept [{field, order}] or a Mongo sort dict {field: -1}."""
        if s is None:
            return None
        if isinstance(s, dict):
            return [{"field": k, "order": v} for k, v in s.items()]
        return list(s)

    def _scoped_filter(filter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply workflow/campaign scope from the HTTP context."""
        scoped = dict(filter or {})
        for key in ("workflow_id", "campaign_id"):
            if (context or {}).get(key):
                scoped[key] = context[key]
        return scoped

    @tool
    def query_tasks(
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Any] = None,
        limit: int = 100,
        sort: Optional[Any] = None,
    ) -> str:
        """Query task provenance records with a Mongo-style filter.

        projection: list of field names, or a Mongo projection dict {"field": 1}.
        sort: list of {"field": "...", "order": 1|-1}, or a Mongo sort dict {"field": -1}.
        """
        return _run_mcp(
            "query_tasks",
            filter=_scoped_filter(filter),
            projection=_coerce_projection(projection),
            limit=limit,
            sort=_coerce_sort(sort),
        )

    @tool
    def query_workflows(filter: Optional[Dict[str, Any]] = None, limit: int = 100) -> str:
        """Query workflow provenance records with a Mongo-style filter."""
        return _run_mcp("query_workflows", filter=_scoped_filter(filter), limit=limit)

    @tool
    def get_task_summary(filter: Optional[Dict[str, Any]] = None) -> str:
        """Summarize tasks: status counts, per-activity durations, and time range."""
        return _run_mcp("get_task_summary", filter=_scoped_filter(filter))

    @tool
    def list_campaigns(campaign_id: Optional[str] = None) -> str:
        """List derived campaign summaries (campaigns group workflows and tasks).

        campaign_id: when provided, returns only that campaign's summary.
        Always pass the campaign_id from the user context to scope the result.
        """
        effective_id = campaign_id or (context or {}).get("campaign_id")
        return _run_mcp("list_campaigns", campaign_id=effective_id)

    @tool
    def list_agents() -> str:
        """List derived agent summaries (agents observed in task provenance).

        Automatically scoped to the current workflow when workflow_id is in context.
        """
        workflow_id = (context or {}).get("workflow_id")
        effective_filter = {"workflow_id": workflow_id} if workflow_id else None
        return _run_mcp("list_agents", filter=effective_filter)

    @tool
    def make_chart(card_spec: Dict[str, Any]) -> str:
        """Build a chart from a declarative dashboard card spec; the UI renders the result."""
        scoped_spec = dict(card_spec)
        data_spec = dict(scoped_spec.get("data") or {})
        data_spec["filter"] = _scoped_filter(data_spec.get("filter"))
        scoped_spec["data"] = data_spec
        return _run_mcp("make_chart", card_spec=scoped_spec, context=None)

    @tool
    def highlight_lineage(
        task_ids: Optional[Any] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Highlight the full provenance lineage (ancestors + descendants) of tasks in the Dataflow graph.

        Pass `task_ids` as a list of task ID strings, or a single task ID string.
        Or use `filter` to find the seed tasks first.
        The UI will dim all other nodes and visually trace the lineage chain.
        Always pass a workflow_id in the filter when on a workflow page.
        """
        wf_id = (context or {}).get("workflow_id")
        ids: Optional[List[str]] = None
        if task_ids is not None:
            ids = [task_ids] if isinstance(task_ids, str) else list(task_ids)
        return _run_mcp("highlight_lineage", task_ids=ids, filter=filter, workflow_id=wf_id)

    @tool("generate_result_df")
    def generate_result_df(code: str) -> str:
        """Answer questions about task execution using the in-memory tasks DataFrame.

        Pass PANDAS CODE (assigned to `result`) that queries the DataFrame variable `df`.
        The DataFrame schema and available columns are in the system prompt.
        Do NOT pass natural language — generate and pass valid pandas code directly.

        Use for: activities, task inputs/outputs, timing, telemetry, agent actions,
        configuration parameters, task counts, lineage, and execution order.
        Do NOT use for inherent properties of stored artifacts — use generate_objects_df.
        """
        return _run_mcp("run_df_query", code=code, context_kind="tasks")

    @tool("generate_plot_code")
    def generate_plot_code(result_code: str, plot_code: str = "") -> str:
        """Generate plotting output using the in-memory task DataFrame.

        result_code: pandas code (assigned to `result`) to produce the data for plotting.
        plot_code: matplotlib/plotly code to render the chart (may reference `result`).
        """
        result_str = _run_mcp("run_df_query", code=result_code, context_kind="tasks")
        if not plot_code:
            return result_str
        try:
            import json as _json
            parsed = _json.loads(result_str)
            if isinstance(parsed.get("result"), dict):
                parsed["result"]["plot_code"] = plot_code
                return _json.dumps(parsed)
        except Exception:
            pass
        return result_str

    @tool
    def extract_or_fix_python_code(raw_text: str, runtime_error: Optional[str] = None) -> str:
        """Extract or repair pandas code using the MCP server's in-memory task DataFrame columns."""
        return _run_mcp(
            "extract_or_fix_python_code",
            raw_text=raw_text,
            runtime_error=runtime_error,
            context_kind="tasks",
        )

    @tool
    def get_workflow_context() -> str:
        """Return the workflow record loaded in the agent's in-memory context (DF path counterpart to query_workflows).

        Use this tool ONLY when the question is specifically about workflow-level metadata: workflow name,
        campaign, start/end timestamps, owner/user, description, hardware, or workflow structure.
        Do NOT call this tool for questions about tasks, activities, agents, data artifacts, or model parameters —
        use generate_result_df or generate_objects_df for those instead.
        """
        return _run_mcp("get_workflow_context")

    @tool
    def query_objects(
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Any] = None,
        limit: int = 100,
    ) -> str:
        """Query stored data-object records (ML models, datasets, blobs) by their inherent properties.

        Use when the question asks about WHAT AN ARTIFACT IS — e.g. model training technique,
        optimizer, number of parameters or weights, purpose or designed uses, science domain, loss,
        dataset sample count or split ratio, object type, file size, or any custom_metadata field.
        Filter by ``workflow_id`` or ``object_type`` (``"ml_model"``, ``"dataset"``).
        ``custom_metadata`` sub-fields use dot-notation, e.g. ``custom_metadata.model_profile.params``.

        Do NOT use for questions about task execution — use query_tasks for those.
        """
        # Objects have no campaign_id field; scope by workflow_id only.
        obj_filter = dict(filter or {})
        if (context or {}).get("workflow_id"):
            obj_filter["workflow_id"] = context["workflow_id"]
        return _run_mcp(
            "query_objects",
            filter=obj_filter,
            projection=_coerce_projection(projection),
            limit=limit,
        )

    @tool("generate_objects_df")
    def generate_objects_df(code: str) -> str:
        """Answer questions about the inherent properties of stored data artifacts using the objects DataFrame.

        Pass PANDAS CODE (assigned to `result`) that queries the objects DataFrame variable `df`.
        Use when the question asks about WHAT AN ARTIFACT IS or WHAT IT CONTAINS — not what task
        processed it. Examples: model training technique, parameter count, purpose, science domain,
        loss, dataset sample count, object type, file size, or any custom_metadata field.

        Do NOT use for questions about task execution — use generate_result_df for those.
        """
        return _run_mcp("run_df_query", code=code, context_kind="objects")

    db_tools = [
        query_tasks,
        query_workflows,
        get_task_summary,
        list_campaigns,
        list_agents,
        make_chart,
        highlight_lineage,
        query_objects,
    ]
    df_tools = [
        generate_result_df,
        generate_plot_code,
        extract_or_fix_python_code,
        get_workflow_context,
        list_agents,
        generate_objects_df,
    ]
    tool_context = (context or {}).get("tool_context", "db")
    tools = df_tools if tool_context == "df" else db_tools

    if allow_dashboard_edit:

        @tool
        def get_dashboard(dashboard_id: str) -> str:
            """Get a stored dashboard spec by id."""
            return _run_mcp("get_dashboard", dashboard_id=dashboard_id)

        @tool
        def update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> str:
            """Replace a stored dashboard spec with a complete revised spec."""
            return _run_mcp("update_dashboard", dashboard_id=dashboard_id, spec=spec)

        tools += [get_dashboard, update_dashboard]
    return tools
