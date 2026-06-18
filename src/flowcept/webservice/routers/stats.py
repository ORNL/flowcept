"""Stats endpoints: task summaries, telemetry timeseries, and the dashboard chart-data resolver."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.routers.query import _validate_filter_shape
from flowcept.commons.dashboard_schemas import ChartData
from flowcept.commons import provenance_stats as stats
from flowcept.commons.utils import normalize_docs

router = APIRouter(prefix="/stats", tags=["stats"])


class TimeseriesRequest(BaseModel):
    """Request body for telemetry/field timeseries extraction."""

    filter: Dict[str, Any] = Field(default_factory=dict)
    fields: List[str]
    x: str = "started_at"
    limit: int = Field(default=1000, ge=1, le=5000)


class ChartDataRequest(BaseModel):
    """Request body for the declarative chart-data resolver."""

    data: ChartData
    context: Optional[Dict[str, Any]] = None


def _json_filter(filter_json: Optional[str]) -> Dict[str, Any]:
    if not filter_json:
        return {}
    try:
        parsed = json.loads(filter_json)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid filter JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="filter_json must decode to a JSON object.")
    return parsed


@router.get("/tasks/summary", response_model=Dict[str, Any])
def get_task_summary(
    workflow_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    filter_json: Optional[str] = None,
    db: DBAPI = Depends(get_db_api),
) -> Dict[str, Any]:
    """Summarize tasks (status counts, per-activity durations, time range)."""
    query_filter = _json_filter(filter_json)
    for key, value in (("workflow_id", workflow_id), ("campaign_id", campaign_id), ("agent_id", agent_id)):
        if value is not None:
            query_filter[key] = value
    _validate_filter_shape(query_filter)
    return normalize_docs([stats.task_summary(db, query_filter)])[0]


@router.post("/timeseries", response_model=Dict[str, Any])
def post_timeseries(payload: TimeseriesRequest, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Extract plottable rows of dot-notated fields from tasks."""
    _validate_filter_shape(payload.filter)
    rows = stats.telemetry_timeseries(
        db,
        filter=payload.filter,
        fields=payload.fields,
        x_field=payload.x,
        limit=payload.limit,
    )
    rows = normalize_docs(rows)
    return {"rows": rows, "count": len(rows)}


@router.post("/chart_data", response_model=Dict[str, Any])
def post_chart_data(payload: ChartDataRequest, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Resolve a declarative dashboard chart data binding into rows."""
    _validate_filter_shape(payload.data.filter)
    if payload.context:
        _validate_filter_shape(payload.context)
    result = stats.resolve_chart_data(db, payload.data, context=payload.context)
    result["rows"] = normalize_docs(result["rows"])
    return result
