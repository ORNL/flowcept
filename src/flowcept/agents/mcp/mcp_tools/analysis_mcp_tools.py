"""Thin MCP wrappers for provenance analysis tools.

All analysis logic lives in :mod:`flowcept.agents.prov_analysis`.  The ``df_*``
tools run over the records loaded in the agent's in-memory context (the same
context ``df_query_mcp_tools`` queries); the ``db_*`` variants pull records
from the database via ``DBAPI``.  ``compare_executions`` compares two
workflows, preferring in-memory records and falling back to the DB.
"""

from typing import Any, Dict, List, Optional

from flowcept.agents.mcp.context_manager import EMPTY_DF_MESSAGE, ctx_manager, get_df_context, mcp_flowcept
from flowcept.agents.prov_analysis import tools as _core
from flowcept.agents.tool_result import ToolResult
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


def _context_records() -> List[Dict[str, Any]]:
    """Collect provenance records from the agent's in-memory context.

    Prefers the raw task dicts kept by the context manager (they retain nested
    ``used``/``generated``/``custom_metadata`` fields); falls back to the
    flattened tasks DataFrame when no raw tasks are held.
    """
    records: List[Dict[str, Any]] = []
    workflow = ctx_manager.context.workflow_msg_obj
    if workflow:
        records.append(workflow)
    tasks = ctx_manager.context.tasks or []
    if tasks:
        records.extend(tasks)
    else:
        df, _, _, _ = get_df_context(context_kind="tasks")
        if df is not None and len(df):
            records.extend(df.to_dict("records"))
    return records


def _db_records(workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load workflow and task records for one workflow (or all tasks) from the DB."""
    from flowcept.flowcept_api.db_api import DBAPI

    db = DBAPI()
    filter = {"workflow_id": workflow_id} if workflow_id else {}
    records: List[Dict[str, Any]] = []
    for wf in db.workflow_query(filter=filter) or []:
        wf = dict(wf)
        wf.setdefault("type", "workflow")
        records.append(wf)
    for task in db.task_query(filter=filter) or []:
        task = dict(task)
        task.setdefault("type", "task")
        records.append(task)
    return records


def _db_analysis(tool_name: str, analysis_fn, workflow_id: Optional[str], **kwargs) -> ToolResult:
    """Run one analysis over DB records, converting DB failures to a ToolResult error."""
    try:
        records = _db_records(workflow_id)
    except Exception as e:
        return ToolResult(code=499, result=f"Error in {tool_name}: could not query DB: {e}", tool_name=tool_name)
    return analysis_fn(records, **kwargs)


# ---------------------------------------------------------------------------
# DF variants — analyze the records loaded in the agent's in-memory context
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_summarize_execution(workflow_id: str = None) -> ToolResult:
    """Summarize the loaded execution: counts by activity/subtype, statuses, durations, token usage.

    Optionally pass ``workflow_id`` to restrict the summary to one workflow.
    """
    records = _context_records()
    if not records:
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_summarize_execution")
    return _core.summarize_execution(records, workflow_id=workflow_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_analyze_errors() -> ToolResult:
    """Analyze failures in the loaded execution: per-activity error rates and stderr excerpts."""
    records = _context_records()
    if not records:
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_analyze_errors")
    return _core.analyze_errors(records)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_agent_behavior() -> ToolResult:
    """Profile per-agent behavior in the loaded execution: turns, tool calls, LLM calls, token usage."""
    records = _context_records()
    if not records:
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_agent_behavior")
    return _core.analyze_agent_behavior(records)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_find_slowest(limit: int = 10) -> ToolResult:
    """Find the slowest tasks of the loaded execution, longest elapsed first."""
    records = _context_records()
    if not records:
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_find_slowest")
    return _core.find_slowest_tasks(records, limit=limit)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def df_cross_framework_links() -> ToolResult:
    """List cross-framework provenance links (source_agent_id edges) in the loaded execution."""
    records = _context_records()
    if not records:
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="df_cross_framework_links")
    return _core.cross_framework_links(records)


# ---------------------------------------------------------------------------
# DB variants — analyze records pulled from the database via DBAPI
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_summarize_execution(workflow_id: str = None) -> ToolResult:
    """Summarize an execution from DB records: counts, statuses, durations, token usage."""
    return _db_analysis("db_summarize_execution", _core.summarize_execution, workflow_id, workflow_id=workflow_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_analyze_errors(workflow_id: str = None) -> ToolResult:
    """Analyze failures from DB records: per-activity error rates and stderr excerpts."""
    return _db_analysis("db_analyze_errors", _core.analyze_errors, workflow_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_agent_behavior(workflow_id: str = None) -> ToolResult:
    """Profile per-agent behavior from DB records: turns, tool calls, LLM calls, token usage."""
    return _db_analysis("db_agent_behavior", _core.analyze_agent_behavior, workflow_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_find_slowest(workflow_id: str = None, limit: int = 10) -> ToolResult:
    """Find the slowest tasks from DB records, longest elapsed first."""
    return _db_analysis("db_find_slowest", _core.find_slowest_tasks, workflow_id, limit=limit)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_cross_framework_links(workflow_id: str = None) -> ToolResult:
    """List cross-framework provenance links (source_agent_id edges) from DB records."""
    return _db_analysis("db_cross_framework_links", _core.cross_framework_links, workflow_id)


# ---------------------------------------------------------------------------
# Comparison — two workflow executions
# ---------------------------------------------------------------------------


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def compare_executions(workflow_id_a: str, workflow_id_b: str) -> ToolResult:
    """Compare two workflow executions per activity: count, duration, and error-rate deltas.

    Records for each workflow are taken from the agent's in-memory context when
    present there, otherwise queried from the database.
    """
    in_memory = _context_records()

    def records_for(workflow_id: str) -> List[Dict[str, Any]]:
        matching = [r for r in in_memory if r.get("workflow_id") == workflow_id]
        if matching:
            return matching
        return _db_records(workflow_id)

    return _core.compare_executions(records_for(workflow_id_a), records_for(workflow_id_b))
