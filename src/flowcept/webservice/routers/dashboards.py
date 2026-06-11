"""Dashboard CRUD endpoints for storing and serving dashboard JSON specs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException

from flowcept.webservice.routers.query import _validate_filter_shape
from flowcept.webservice.schemas.common import ListResponse
from flowcept.webservice.schemas.dashboards import DashboardSpec
from flowcept.webservice.services.dashboard_store import get_dashboard_store

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_spec_filters(spec: DashboardSpec) -> None:
    _validate_filter_shape(spec.context)
    for chart in spec.charts:
        if chart.data is not None:
            _validate_filter_shape(chart.data.filter)


@router.get("", response_model=ListResponse)
def list_dashboards(store=Depends(get_dashboard_store)) -> ListResponse:
    """List all stored dashboards."""
    dashboards = store.list()
    return ListResponse(items=dashboards, count=len(dashboards), limit=0)


@router.post("", response_model=Dict[str, Any], status_code=201)
def create_dashboard(spec: DashboardSpec, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Create a dashboard; the server assigns its id and timestamps."""
    _validate_spec_filters(spec)
    spec.dashboard_id = str(uuid4())
    spec.created_at = spec.updated_at = _now()
    doc = spec.model_dump()
    if not store.save(doc):
        raise HTTPException(status_code=500, detail="Could not save dashboard.")
    return doc


@router.get("/{dashboard_id}", response_model=Dict[str, Any])
def get_dashboard(dashboard_id: str, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Get a dashboard by id."""
    doc = store.get(dashboard_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"Dashboard not found: {dashboard_id}")
    return doc


@router.put("/{dashboard_id}", response_model=Dict[str, Any])
def update_dashboard(dashboard_id: str, spec: DashboardSpec, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Replace a dashboard spec, preserving its id and creation time."""
    existing = store.get(dashboard_id)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Dashboard not found: {dashboard_id}")
    _validate_spec_filters(spec)
    spec.dashboard_id = dashboard_id
    spec.created_at = existing.get("created_at")
    spec.updated_at = _now()
    doc = spec.model_dump()
    if not store.save(doc):
        raise HTTPException(status_code=500, detail="Could not save dashboard.")
    return doc


@router.delete("/{dashboard_id}", response_model=Dict[str, Any])
def delete_dashboard(dashboard_id: str, store=Depends(get_dashboard_store)) -> Dict[str, Any]:
    """Delete a dashboard by id."""
    if not store.delete(dashboard_id):
        raise HTTPException(status_code=404, detail=f"Dashboard not found: {dashboard_id}")
    return {"deleted": dashboard_id}
