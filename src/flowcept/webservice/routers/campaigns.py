"""Campaign endpoints (derived — campaigns exist as a grouping key, not a collection)."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query

from fastapi.responses import Response

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse
from flowcept.commons import provenance_stats as stats
from flowcept.webservice.services.reports import workflow_card_response
from flowcept.commons.utils import normalize_docs
from flowcept.webservice.services.sorting import sort_docs_by_first_date_field

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.get("", response_model=ListResponse)
def list_campaigns(
    limit: int = Query(default=100, ge=1, le=1000),
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List derived campaign summaries, most recently active first."""
    campaigns = stats.derive_campaigns(db)
    campaigns = sort_docs_by_first_date_field(campaigns, ["last_ts", "first_ts"])
    campaigns = campaigns[:limit]
    normalized = normalize_docs(campaigns)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.get("/{campaign_id}", response_model=Dict[str, Any])
def get_campaign(campaign_id: str, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Get one campaign: derived summary, its workflows, and a task summary."""
    workflows = db.workflow_query(filter={"campaign_id": campaign_id}) or []
    task_summary = stats.task_summary(db, {"campaign_id": campaign_id})
    if not workflows and task_summary["count"] == 0:
        raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")

    workflows = sort_docs_by_first_date_field(
        workflows,
        ["utc_timestamp", "created_at", "updated_at", "timestamp", "started_at", "ended_at"],
    )
    summary = next(
        (c for c in stats.derive_campaigns(db) if c["campaign_id"] == campaign_id),
        {"campaign_id": campaign_id},
    )
    return {
        "campaign": normalize_docs([summary])[0],
        "workflows": normalize_docs(workflows),
        "task_summary": normalize_docs([task_summary])[0],
    }


@router.delete("/{campaign_id}", response_model=Dict[str, Any])
def delete_campaign(campaign_id: str, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Recursively delete a campaign and all its workflows, tasks, and objects."""
    workflows = db.workflow_query(filter={"campaign_id": campaign_id}) or []
    if not workflows:
        raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")
    counts = DBAPI._dao().delete_campaign_data(campaign_id)
    return {"deleted": counts}


@router.get("/{campaign_id}/workflow_card")
def get_campaign_workflow_card(
    campaign_id: str,
    format: str = Query(default="json"),
    db: DBAPI = Depends(get_db_api),
) -> Response:
    """Get a campaign workflow card as structured JSON or rendered markdown."""
    workflows = db.workflow_query(filter={"campaign_id": campaign_id}) or []
    if not workflows:
        raise HTTPException(status_code=404, detail=f"Campaign not found: {campaign_id}")
    return workflow_card_response(format=format, campaign_id=campaign_id)
