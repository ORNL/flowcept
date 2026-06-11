"""Workflow endpoints."""

import json
import os
import tempfile
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from flowcept import Flowcept
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse, QueryRequest
from flowcept.webservice.services.reports import provenance_card_response
from flowcept.webservice.services.serializers import normalize_docs
from flowcept.webservice.services.sorting import sort_docs_by_first_date_field

router = APIRouter(prefix="/workflows", tags=["workflows"])


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
def list_workflows(
    limit: int = Query(default=100, ge=1, le=1000),
    user: str | None = None,
    campaign_id: str | None = None,
    parent_workflow_id: str | None = None,
    name: str | None = None,
    filter_json: str | None = None,
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List workflows with optional basic filters."""
    query_filter = _json_filter(filter_json)
    if user is not None:
        query_filter["user"] = user
    if campaign_id is not None:
        query_filter["campaign_id"] = campaign_id
    if parent_workflow_id is not None:
        query_filter["parent_workflow_id"] = parent_workflow_id
    if name is not None:
        query_filter["name"] = name

    docs = db.workflow_query(filter=query_filter) or []
    docs = sort_docs_by_first_date_field(
        docs,
        ["utc_timestamp", "created_at", "updated_at", "timestamp", "started_at", "ended_at"],
    )
    docs = docs[:limit]
    normalized = normalize_docs(docs)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.get("/{workflow_id}", response_model=Dict[str, Any])
def get_workflow(workflow_id: str, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Get a workflow by id."""
    doc = db.get_workflow_object(workflow_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    normalized = normalize_docs([doc.to_dict()])
    return normalized[0]


@router.post("/query", response_model=ListResponse)
def query_workflows(payload: QueryRequest, db: DBAPI = Depends(get_db_api)) -> ListResponse:
    """Run an advanced read-only workflows query."""
    sort = None if payload.sort is None else [(s.field, s.order) for s in payload.sort]
    docs = db.query(
        collection="workflows",
        filter=payload.filter,
        projection=payload.projection,
        limit=payload.limit,
        sort=sort,
        aggregation=payload.aggregation,
        remove_json_unserializables=payload.remove_json_unserializables,
    )
    docs = docs or []
    normalized = normalize_docs(docs)
    return ListResponse(items=normalized, count=len(normalized), limit=payload.limit)


@router.get("/{workflow_id}/provenance_card")
def get_workflow_provenance_card(
    workflow_id: str,
    format: str = Query(default="json"),
    db: DBAPI = Depends(get_db_api),
) -> Response:
    """Get a workflow provenance card as structured JSON or rendered markdown."""
    wf_obj = db.get_workflow_object(workflow_id)
    if wf_obj is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")
    return provenance_card_response(format=format, workflow_id=workflow_id)



@router.post("/{workflow_id}/reports/provenance-card/download")
def download_workflow_provenance_card(workflow_id: str, db: DBAPI = Depends(get_db_api)) -> Response:
    """Generate and download a workflow provenance card markdown file."""
    wf_obj = db.get_workflow_object(workflow_id)
    if wf_obj is None:
        raise HTTPException(status_code=404, detail=f"Workflow not found: {workflow_id}")

    fd, output_path = tempfile.mkstemp(prefix=f"provenance_card_{workflow_id}_", suffix=".md")
    os.close(fd)
    try:
        Flowcept.generate_report(
            report_type="provenance_card",
            format="markdown",
            output_path=output_path,
            workflow_id=workflow_id,
        )
        with open(output_path, "rb") as handle:
            payload = handle.read()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not generate provenance card: {exc}") from exc
    finally:
        try:
            os.remove(output_path)
        except Exception:
            pass

    filename = f"provenance_card_{workflow_id}.md"
    return Response(
        content=payload,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
