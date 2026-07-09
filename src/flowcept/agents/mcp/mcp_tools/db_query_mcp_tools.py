"""Thin MCP wrappers exposing DB provenance query tools to external agent clients.

One-liner delegates to :mod:`flowcept.agents.data_query_tools.db_query_tools`.
No business logic here — all logic lives in ``data_query_tools/``.
"""

from typing import Any, Dict, List, Optional

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.mcp.context_manager import mcp_flowcept
from flowcept.agents.data_query_tools import db_query_tools
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_query_tasks(
    filter: Optional[Dict[str, Any]] = None,
    projection: Optional[List[str]] = None,
    limit: int = 100,
    sort: Optional[List[Dict[str, Any]]] = None,
) -> ToolResult:
    """Query task provenance records in the database with a Mongo-style filter."""
    return db_query_tools.query_tasks(filter=filter, projection=projection, limit=limit, sort=sort)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_query_workflows(filter: Optional[Dict[str, Any]] = None, limit: int = 100) -> ToolResult:
    """Query workflow provenance records in the database with a Mongo-style filter."""
    return db_query_tools.query_workflows(filter=filter, limit=limit)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_get_task_summary(filter: Optional[Dict[str, Any]] = None) -> ToolResult:
    """Summarize tasks matching a filter: status counts, per-activity durations, time range."""
    return db_query_tools.get_task_summary(filter=filter)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_list_campaigns(campaign_id: Optional[str] = None) -> ToolResult:
    """List derived campaign summaries (campaigns group workflows and tasks)."""
    return db_query_tools.list_campaigns(campaign_id=campaign_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_list_agents(filter: Optional[Dict[str, Any]] = None) -> ToolResult:
    """List derived agent summaries (agents observed in task provenance)."""
    return db_query_tools.list_agents(filter=filter)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_query_objects(
    filter: Optional[Dict[str, Any]] = None,
    projection: Optional[Any] = None,
    limit: int = 100,
) -> ToolResult:
    """Query stored data-object records (ML models, datasets, blobs) with a Mongo-style filter.

    Use for model parameters, dataset metadata, artifact sizes, or file types.
    """
    if isinstance(projection, dict):
        projection = [k for k, v in projection.items() if v]
    return db_query_tools.query_objects(filter=filter, projection=projection or None, limit=limit)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_highlight_lineage(
    task_ids: Optional[List[str]] = None,
    filter: Optional[Dict[str, Any]] = None,
    workflow_id: Optional[str] = None,
) -> ToolResult:
    """Return seed tasks for UI lineage highlighting."""
    return db_query_tools.highlight_lineage(task_ids=task_ids, filter=filter, workflow_id=workflow_id)


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def db_fix_query(
    query_params: Dict[str, Any],
    error: str,
) -> ToolResult:
    """Repair bad DB query parameters (filter/projection/sort) that caused a runtime error.

    Pass the original query_params dict and the error message; returns a corrected query_params.
    Symmetric counterpart to df_fix_query which repairs pandas code.
    """
    from flowcept.agents.llm.builders import build_llm_model
    from flowcept.agents.data_query_tools import db_query_tools as _core

    return _core.fix_query(build_llm_model(track_tools=False), query_params=query_params, error=error)
