"""Agent endpoints (derived from task ``agent_id``/``source_agent_id`` fields)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse
from flowcept.webservice.services import stats
from flowcept.webservice.services.serializers import normalize_docs
from flowcept.webservice.services.sorting import sort_docs_by_first_date_field

router = APIRouter(prefix="/agents", tags=["agents"])


@router.get("", response_model=ListResponse)
def list_agents(
    limit: int = Query(default=100, ge=1, le=1000),
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List derived agent summaries, most recently active first."""
    agents = stats.derive_agents(db)
    agents = sort_docs_by_first_date_field(agents, ["registered_at", "last_active"])
    agents = agents[:limit]
    normalized = normalize_docs(agents)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.get("/{agent_id}", response_model=Dict[str, Any])
def get_agent(agent_id: str, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Get one agent's derived summary and per-activity task summary."""
    agents = [a for a in stats.derive_agents(db) if a["agent_id"] == agent_id]
    if not agents:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    task_summary = stats.task_summary(db, {"agent_id": agent_id})
    return {
        "agent": normalize_docs(agents)[0],
        "task_summary": normalize_docs([task_summary])[0],
    }


@router.get("/{agent_id}/tasks", response_model=ListResponse)
def get_agent_tasks(
    agent_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List tasks executed by or sent from an agent."""
    docs = (
        db.task_query(
            filter={"$or": [{"agent_id": agent_id}, {"source_agent_id": agent_id}]},
            limit=limit,
        )
        or []
    )
    docs = sort_docs_by_first_date_field(
        docs,
        ["started_at", "utc_timestamp", "ended_at", "registered_at"],
    )
    normalized = normalize_docs(docs)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.delete("/cleanup/empty", response_model=Dict[str, Any])
def delete_empty_agents(db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Delete all agents from the database that don't have associated task_id."""
    stored_agents = db.agent_query(filter={}) or []
    deleted_count = 0
    for agent in stored_agents:
        agent_id = agent.get("agent_id")
        if not agent_id:
            continue
        tasks = db.task_query(
            filter={"$or": [{"agent_id": agent_id}, {"source_agent_id": agent_id}]},
            limit=1,
        )
        if not tasks:
            db.delete_agents_with_filter({"agent_id": agent_id})
            deleted_count += 1
    return {"deleted_count": deleted_count}
