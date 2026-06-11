"""Shared request/response schemas for webservice endpoints."""

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class SortSpec(BaseModel):
    """Sort field/order pair."""

    field: str = Field(..., min_length=1)
    order: Literal[1, -1] = 1


class AggregationSpec(BaseModel):
    """Aggregation operator and source field."""

    operator: Literal["avg", "sum", "min", "max"]
    field: str = Field(..., min_length=1)


class QueryRequest(BaseModel):
    """Read-only query payload."""

    filter: Dict[str, Any] = Field(default_factory=dict)
    projection: List[str] | None = None
    limit: int = Field(default=100, ge=0, le=1000)
    sort: List[SortSpec] | None = None
    aggregation: List[AggregationSpec] | None = None
    remove_json_unserializables: bool = True


class ObjectQueryRequest(QueryRequest):
    """Object query payload with optional payload inclusion."""

    include_data: bool = False


class ListResponse(BaseModel):
    """Generic list envelope for collection endpoints."""

    items: List[Dict[str, Any]]
    count: int
    limit: int


class ErrorResponse(BaseModel):
    """Error response envelope."""

    detail: str
