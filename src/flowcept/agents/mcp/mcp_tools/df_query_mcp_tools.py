"""Thin MCP wrappers for DF (DataFrame) query tools.

All tools delegate to :mod:`flowcept.agents.data_query_tools.df_query_tools`.
``run_df_query`` is an internal helper called by the specific ``df_*`` tools;
it is not referenced directly from ``tool_registry.py``.
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


# ---------------------------------------------------------------------------
# Internal helper — not exposed to tool_registry.py directly
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def run_df_query(code: str, context_kind: str = "tasks") -> ToolResult:
    """Execute pandas code against the current context DataFrame.

    Pure executor — no internal LLM call.  The code must assign its output
    to ``result``.

    Parameters
    ----------
    code : str
        Pandas code that assigns output to ``result``.
    context_kind : str, optional
        ``"tasks"`` or ``"objects"``.
    """
    df, _, _, _ = get_df_context(context_kind=context_kind)
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE)
    return _core.execute_df_code(user_code=code, df=df)


# ---------------------------------------------------------------------------
# DF query tools — symmetric counterparts to db_query_mcp_tools
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_query_tasks(code: str) -> ToolResult:
    """Query task provenance using pandas code against the in-memory tasks DataFrame.

    ``code`` must be valid pandas code that assigns its output to ``result``.
    The DataFrame variable is ``df``; its schema is in the system prompt.
    """
    return run_df_query(code=code, context_kind="tasks")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_query_workflows() -> ToolResult:
    """Return the workflow record(s) loaded in the agent's in-memory context.

    Strips heavy infrastructure fields; adds a lightweight hardware_summary.
    Symmetric counterpart to db_query_workflows.
    """
    wf = ctx_manager.context.workflow_msg_obj
    if not wf:
        return ToolResult(code=404, result="No workflow loaded in agent context.", tool_name="df_query_workflows")
    pruned = {k: v for k, v in wf.items() if k not in _WORKFLOW_HEAVY_FIELDS}
    machine_info = wf.get("machine_info")
    if machine_info and isinstance(machine_info, dict):
        for node_data in machine_info.values():
            if isinstance(node_data, dict):
                hw: dict = {}
                if "platform" in node_data:
                    hw["platform"] = node_data["platform"]
                if "cpu" in node_data:
                    cpu = node_data["cpu"]
                    hw["cpu"] = {k: cpu[k] for k in ("brand_raw", "arch", "count") if k in cpu}
                if hw:
                    pruned["hardware_summary"] = hw
                break
    return ToolResult(code=301, result={"items": [pruned], "count": 1}, tool_name="df_query_workflows")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_query_objects(code: str) -> ToolResult:
    """Query stored data-object records using pandas code against the in-memory objects DataFrame.

    ``code`` must assign its output to ``result``.
    Symmetric counterpart to db_query_objects.
    """
    return run_df_query(code=code, context_kind="objects")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_get_task_summary() -> ToolResult:
    """Summarize tasks in the in-memory DataFrame: activity types, status counts, time range.

    Symmetric counterpart to db_get_task_summary.
    """
    df, _, _, _ = get_df_context(context_kind="tasks")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_get_task_summary")
    summary: dict = {}
    if "activity_id" in df.columns:
        summary["activity_ids"] = sorted(df["activity_id"].dropna().unique().tolist())
        summary["activity_task_counts"] = df["activity_id"].value_counts().to_dict()
    if "status" in df.columns:
        summary["status_counts"] = df["status"].value_counts().to_dict()
    dur_col = next((c for c in ("telemetry_summary.duration_sec",) if c in df.columns), None)
    if dur_col and "activity_id" in df.columns:
        summary["activity_avg_duration_sec"] = df.groupby("activity_id")[dur_col].mean().dropna().to_dict()
    if "started_at" in df.columns:
        summary["time_range"] = {
            "start": str(df["started_at"].min()),
            "end": str(df["ended_at"].max()) if "ended_at" in df.columns else None,
        }
    return ToolResult(code=301, result=summary, tool_name="df_get_task_summary")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_get_objects_summary() -> ToolResult:
    """Summarize stored objects in the in-memory objects DataFrame: available types, counts, and tracked columns.

    Symmetric counterpart to df_get_task_summary but for data objects (artifacts).
    Call this first when the user asks about artifact properties, to discover what object types
    and metadata columns are actually tracked before writing a specific query.
    """
    df, _, _, _ = get_df_context(context_kind="objects")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_get_objects_summary")
    summary: dict = {"available_columns": sorted(df.columns.tolist())}
    type_col = next((c for c in ("object_type", "type") if c in df.columns), None)
    if type_col:
        summary["object_type_counts"] = df[type_col].value_counts().to_dict()
        summary["object_types"] = sorted(df[type_col].dropna().unique().tolist())
    summary["total_objects"] = len(df)
    return ToolResult(code=301, result=summary, tool_name="df_get_objects_summary")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_list_campaigns() -> ToolResult:
    """List campaign summaries derived from the in-memory tasks DataFrame.

    Symmetric counterpart to db_list_campaigns.
    """
    code = (
        "if 'campaign_id' in df.columns:\n"
        "    result = df.groupby('campaign_id').agg(\n"
        "        task_count=('task_id', 'count') if 'task_id' in df.columns else ('campaign_id', 'count'),\n"
        "        workflow_count=('workflow_id', 'nunique') if 'workflow_id' in df.columns else "
        "('campaign_id', 'nunique'),\n"
        "    ).reset_index().to_dict(orient='records')\n"
        "else:\n"
        "    result = []"
    )
    df, _, _, _ = get_df_context(context_kind="tasks")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_list_campaigns")
    return _core.execute_df_code(user_code=code, df=df)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_list_agents() -> ToolResult:
    """List agent summaries derived from the in-memory tasks DataFrame.

    Each entry includes the agent_id, task_count, and name (when available from
    received agent records). Symmetric counterpart to db_list_agents.
    """
    df, _, _, _ = get_df_context(context_kind="tasks")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_list_agents")
    if "agent_id" not in df.columns:
        return ToolResult(code=200, result=[], tool_name="df_list_agents")
    summary = df.groupby("agent_id").agg(task_count=("agent_id", "count")).reset_index()
    agents_store = ctx_manager.context.agents
    summary["name"] = summary["agent_id"].map(lambda aid: (agents_store.get(aid) or {}).get("name"))
    return ToolResult(code=200, result=summary.to_dict(orient="records"), tool_name="df_list_agents")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_highlight_lineage(task_ids: list = None, code: str = None) -> ToolResult:
    """Return seed task IDs for UI lineage highlighting from the in-memory tasks DataFrame.

    Pass ``task_ids`` directly, or ``code`` (pandas code assigning a list to ``result``)
    to select seed tasks from the DataFrame.
    Symmetric counterpart to db_highlight_lineage.
    """
    df, _, _, _ = get_df_context(context_kind="tasks")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_highlight_lineage")
    if task_ids:
        return ToolResult(code=301, result={"task_ids": list(task_ids)}, tool_name="df_highlight_lineage")
    if code:
        result = _core.execute_df_code(user_code=code, df=df)
        if result.code >= 400:
            return result
        ids = result.result if isinstance(result.result, list) else []
        return ToolResult(code=301, result={"task_ids": ids}, tool_name="df_highlight_lineage")
    return ToolResult(code=400, result="Provide task_ids or code.", tool_name="df_highlight_lineage")


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_fix_query(raw_text: str, runtime_error: str = None) -> ToolResult:
    """Extract or repair pandas code using the current agent DataFrame columns.

    Symmetric counterpart to db_fix_query which repairs DB query parameters.
    """
    from flowcept.agents.llm.builders import build_llm_model

    df, _, _, _ = get_df_context(context_kind="tasks")
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_fix_query")
    return _core.extract_or_fix_python_code(
        build_llm_model(track_tools=False),
        raw_text,
        list(df.columns),
        runtime_error=runtime_error,
    )
