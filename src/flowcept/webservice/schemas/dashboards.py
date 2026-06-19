"""Pydantic schemas for dashboards: data bindings, chart specs, layout, and config."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class SortSpec(BaseModel):
    """Sort field/order pair for chart data queries."""

    field: str
    order: Literal[1, -1] = 1


class MetricSpec(BaseModel):
    """A single aggregation over a (dot-notated) field."""

    field: str
    agg: Literal["avg", "sum", "min", "max", "count"]


class ChartData(BaseModel):
    """Declarative data binding for a chart: what to query and how to shape it."""

    source: Literal["tasks", "workflows", "objects", "collection_sizes"] = "tasks"
    filter: Dict[str, Any] = Field(default_factory=dict)
    group_by: Optional[str] = None
    metrics: Optional[List[MetricSpec]] = None
    x: Optional[str] = None
    y: Optional[List[str]] = None
    sort: Optional[List[SortSpec]] = None
    limit: int = Field(default=500, ge=1, le=5000)


class VizSpec(BaseModel):
    """How a chart renders its rows."""

    kind: Literal["line", "bar", "pie", "scatter", "area", "heatmap"] = "line"
    stacked: bool = False


class DashboardChart(BaseModel):
    """One chart inside a dashboard."""

    chart_id: str
    type: Literal["chart", "metric", "table", "markdown"]
    title: str = ""
    live: bool = False
    refresh_interval_sec: Optional[float] = None
    data: Optional[ChartData] = None
    viz: Optional[VizSpec] = None
    content: Optional[str] = None


class LayoutItem(BaseModel):
    """Grid placement of a chart in a 12-column layout."""

    chart_id: str
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1)


class DashboardSpec(BaseModel):
    """A complete dashboard: type, context filter, charts, and layout."""

    dashboard_id: Optional[str] = None
    type: Literal["workflow", "campaign"] = "workflow"
    name: str
    description: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    charts: List[DashboardChart] = Field(default_factory=list)
    layout: List[LayoutItem] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DashboardConfig(BaseModel):
    """A dashboard configuration: one of four types (common/custom × workflow/campaign).

    ``target`` is required for custom types:
    - ``custom_workflow``: the workflow **name** (not id) this config applies to.
    - ``custom_campaign``: the ``campaign_id`` this config applies to.
    Common types leave ``target`` null and apply to every workflow or campaign.
    """

    dashboard_id: Optional[str] = None
    dashboard_type: Literal["common_workflow", "common_campaign", "custom_workflow", "custom_campaign"] = (
        "common_workflow"
    )
    target: Optional[str] = None
    name: str = ""
    description: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    charts: List[DashboardChart] = Field(default_factory=list)
    layout: List[LayoutItem] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
