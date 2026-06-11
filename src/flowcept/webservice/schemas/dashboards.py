"""Pydantic schemas for dashboard specs and declarative card data bindings.

The spec is deliberately declarative (not raw chart configs) so that LLM tools can
reliably generate/modify it and the frontend can validate and render it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from flowcept.webservice.schemas.common import SortSpec


class MetricSpec(BaseModel):
    """A single aggregation over a (dot-notated) field."""

    field: str
    agg: Literal["avg", "sum", "min", "max", "count"]


class CardData(BaseModel):
    """Declarative data binding for a card: what to query and how to shape it."""

    source: Literal["tasks", "workflows", "objects"] = "tasks"
    filter: Dict[str, Any] = Field(default_factory=dict)
    group_by: Optional[str] = None
    metrics: Optional[List[MetricSpec]] = None
    x: Optional[str] = None
    y: Optional[List[str]] = None
    sort: Optional[List[SortSpec]] = None
    limit: int = Field(default=500, ge=1, le=5000)


class VizSpec(BaseModel):
    """How a chart card renders its rows."""

    kind: Literal["line", "bar", "pie", "scatter", "area", "heatmap"] = "line"
    stacked: bool = False


class Card(BaseModel):
    """One dashboard card. Content fields depend on ``type``."""

    card_id: str
    type: Literal["chart", "metric", "table", "markdown", "prov_card"]
    title: str = ""
    live: bool = False
    refresh_interval_sec: Optional[float] = None
    data: Optional[CardData] = None
    viz: Optional[VizSpec] = None
    content: Optional[str] = None
    workflow_id: Optional[str] = None
    campaign_id: Optional[str] = None


class LayoutItem(BaseModel):
    """Grid placement of a card in a 12-column layout."""

    card_id: str
    x: int = Field(ge=0, le=11)
    y: int = Field(ge=0)
    w: int = Field(ge=1, le=12)
    h: int = Field(ge=1)


class DashboardSpec(BaseModel):
    """A complete dashboard: context filter, cards, and layout."""

    dashboard_id: Optional[str] = None
    name: str
    description: str = ""
    context: Dict[str, Any] = Field(default_factory=dict)
    cards: List[Card] = Field(default_factory=list)
    layout: List[LayoutItem] = Field(default_factory=list)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
