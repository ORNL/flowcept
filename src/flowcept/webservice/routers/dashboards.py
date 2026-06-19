"""Dashboard config CRUD and resolution endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query

from flowcept.webservice.routers.query import _validate_filter_shape
from flowcept.webservice.schemas.common import ListResponse
from flowcept.webservice.schemas.dashboards import DashboardConfig
from flowcept.flowcept_api.db_api import DBAPI

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def get_dashboard_store():
    """FastAPI dependency: return the DAO instance for dashboard CRUD."""
    return DBAPI.get_dao_instance()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_config_filters(config: DashboardConfig) -> None:
    _validate_filter_shape(config.context)
    for chart in config.charts:
        if chart.data is not None:
            _validate_filter_shape(chart.data.filter)


@router.get("/resolve", response_model=List[Dict[str, Any]])
def resolve_dashboard(
    workflow_name: Optional[str] = Query(default=None),
    campaign_id: Optional[str] = Query(default=None),
    store=Depends(get_dashboard_store),
) -> List[Dict[str, Any]]:
    """Return merged charts for a workflow or campaign.

    For a workflow: returns charts from all ``common_workflow`` configs merged
    with charts from any ``custom_workflow`` config whose ``target`` matches
    ``workflow_name``.

    For a campaign: returns charts from all ``common_campaign`` configs merged
    with charts from any ``custom_campaign`` config whose ``target`` matches
    ``campaign_id``.
    """
    if workflow_name:
        common = store.list_by_type("common_workflow")
        custom = [c for c in store.list_by_type("custom_workflow") if c.get("target") == workflow_name]
    elif campaign_id:
        common = store.list_by_type("common_campaign")
        custom = [c for c in store.list_by_type("custom_campaign") if c.get("target") == campaign_id]
    else:
        raise HTTPException(status_code=400, detail="Provide workflow_name or campaign_id.")

    charts: List[Dict[str, Any]] = []
    for cfg in common + custom:
        charts.extend(cfg.get("charts", []))
    return charts


@router.get("", response_model=ListResponse)
def list_dashboards(
    dashboard_type: Optional[str] = Query(default=None),
    store=Depends(get_dashboard_store),
) -> ListResponse:
    """List all dashboard configs, optionally filtered by ``dashboard_type``."""
    if dashboard_type:
        items = store.list_by_type(dashboard_type)
    else:
        items = store.list()
    return ListResponse(items=items, count=len(items), limit=0)


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_dashboard(config: DashboardConfig, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Create a dashboard config; the server assigns its id and timestamps."""
    _validate_config_filters(config)
    config.dashboard_id = str(uuid4())
    config.created_at = config.updated_at = _now()
    doc = config.model_dump()
    if not store.save(doc):
        raise HTTPException(status_code=500, detail="Could not save dashboard config.")
    return doc


@router.get("/{dashboard_id}", response_model=Dict[str, Any])
def get_dashboard(dashboard_id: str, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Get a dashboard config by id."""
    doc = store.get(dashboard_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Dashboard not found: {dashboard_id}")
    return doc


@router.put("/{dashboard_id}", response_model=Dict[str, Any])
def update_dashboard(dashboard_id: str, config: DashboardConfig, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Replace a dashboard config, preserving its id and creation time."""
    existing = store.get(dashboard_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Dashboard not found: {dashboard_id}")
    _validate_config_filters(config)
    config.dashboard_id = dashboard_id
    config.created_at = existing.get("created_at")
    config.updated_at = _now()
    doc = config.model_dump()
    if not store.save(doc):
        raise HTTPException(status_code=500, detail="Could not save dashboard config.")
    return doc


@router.delete("/{dashboard_id}", response_model=Dict[str, Any])
def delete_dashboard(dashboard_id: str, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Delete a dashboard config by id."""
    if not store.delete(dashboard_id):
        raise HTTPException(status_code=404, detail=f"Dashboard not found: {dashboard_id}")
    return {"deleted": dashboard_id}
