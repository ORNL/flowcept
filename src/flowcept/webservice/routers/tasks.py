"""Task endpoints."""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse, QueryRequest
from flowcept.webservice.services.serializers import normalize_docs
from flowcept.webservice.services.sorting import sort_docs_by_first_date_field

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _json_filter(filter_json: str | None) -> Dict[str, Any]:
    if not filter_json:
        return {}
    try:
        parsed = json.loads(filter_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid filter JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="filter_json must decode to a JSON object.")
    return parsed


@router.get("", response_model=ListResponse)
def list_tasks(
    limit: int = Query(default=100, ge=1, le=1000),
    workflow_id: str | None = None,
    parent_task_id: str | None = None,
    campaign_id: str | None = None,
    task_id: str | None = None,
    status: str | None = None,
    filter_json: str | None = None,
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List tasks with optional basic filters."""
    query_filter = _json_filter(filter_json)
    if workflow_id is not None:
        query_filter["workflow_id"] = workflow_id
    if parent_task_id is not None:
        query_filter["parent_task_id"] = parent_task_id
    if campaign_id is not None:
        query_filter["campaign_id"] = campaign_id
    if task_id is not None:
        query_filter["task_id"] = task_id
    if status is not None:
        query_filter["status"] = status

    docs = db.task_query(filter=query_filter, limit=0) or []
    docs = sort_docs_by_first_date_field(
        docs,
        ["started_at", "submitted_at", "registered_at", "ended_at", "utc_timestamp", "timestamp"],
    )
    docs = docs[:limit]
    normalized = normalize_docs(docs)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.get("/{task_id}", response_model=Dict[str, Any])
def get_task(task_id: str, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Get a task by id."""
    docs = db.task_query(filter={"task_id": task_id}, limit=1) or []
    if not docs:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    normalized = normalize_docs([docs[0]])
    return normalized[0]


@router.get("/by_workflow/{workflow_id}", response_model=ListResponse)
def list_tasks_by_workflow(
    workflow_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List tasks for a workflow."""
    docs = db.task_query(filter={"workflow_id": workflow_id}, limit=0) or []
    docs = sort_docs_by_first_date_field(
        docs,
        ["started_at", "submitted_at", "registered_at", "ended_at", "utc_timestamp", "timestamp"],
    )
    docs = docs[:limit]
    normalized = normalize_docs(docs)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.post("/query", response_model=ListResponse)
def query_tasks(payload: QueryRequest, db: DBAPI = Depends(get_db_api)) -> ListResponse:
    """Run an advanced read-only task query."""
    if payload.aggregation and payload.projection and len(payload.projection) > 1:
        raise HTTPException(
            status_code=400,
            detail="When aggregation is provided, projection supports at most one field.",
        )

    sort = None if payload.sort is None else [(s.field, s.order) for s in payload.sort]
    aggregation = None
    if payload.aggregation is not None:
        aggregation = [(agg.operator, agg.field) for agg in payload.aggregation]

    docs = db.task_query(
        filter=payload.filter,
        projection=payload.projection,
        limit=payload.limit,
        sort=sort,
        aggregation=aggregation,
        remove_json_unserializables=payload.remove_json_unserializables,
    )
    docs = docs or []
    normalized = normalize_docs(docs)
    return ListResponse(items=normalized, count=len(normalized), limit=payload.limit)
