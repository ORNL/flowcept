"""Unified scoped query endpoint for read-only webservice access."""

from __future__ import annotations

from typing import Any, Dict, List, Literal

from fastapi import APIRouter, Depends, HTTPException

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse, ObjectQueryRequest
from flowcept.webservice.services.serializers import normalize_docs

router = APIRouter(prefix="/query", tags=["query"])

QueryScope = Literal["workflows", "tasks", "objects", "models", "datasets"]
ALLOWED_OPERATORS = {
    "$and",
    "$or",
    "$nor",
    "$not",
    "$exists",
    "$eq",
    "$ne",
    "$gt",
    "$gte",
    "$lt",
    "$lte",
    "$in",
    "$nin",
    "$regex",
}


def _validate_filter_shape(filter_doc: Dict[str, Any]) -> None:
    """Validate query filter shape and allowlist safe Mongo-like operators."""

    def _walk(value: Any, *, in_operator_dict: bool = False) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key.startswith("$"):
                    if key not in ALLOWED_OPERATORS:
                        raise HTTPException(status_code=400, detail=f"Unsupported filter operator: {key}")
                    if key in {"$and", "$or", "$nor"}:
                        if not isinstance(item, list):
                            raise HTTPException(status_code=400, detail=f"{key} must be a list.")
                        for clause in item:
                            _walk(clause)
                        continue
                    if key == "$not":
                        if not isinstance(item, dict):
                            raise HTTPException(status_code=400, detail="$not must be an object.")
                        _walk(item, in_operator_dict=True)
                        continue
                    _walk(item, in_operator_dict=True)
                else:
                    _walk(item, in_operator_dict=False)
        elif isinstance(value, list):
            for item in value:
                _walk(item, in_operator_dict=in_operator_dict)

    _walk(filter_doc)


def _merge_base_filter(base_filter: Dict[str, Any], user_filter: Dict[str, Any]) -> Dict[str, Any]:
    """Merge immutable base filter with user filter using conjunction."""
    if not base_filter:
        return dict(user_filter)
    if not user_filter:
        return dict(base_filter)
    return {"$and": [base_filter, user_filter]}


def _get_scope_metadata(scope: QueryScope) -> tuple[str, Dict[str, Any], bool]:
    """Return `(collection, base_filter, include_data_supported)` for scope."""
    if scope == "workflows":
        return "workflows", {}, False
    if scope == "tasks":
        return "tasks", {}, False
    if scope == "objects":
        return "objects", {}, True
    if scope == "models":
        return "objects", {"type": "ml_model"}, True
    return "objects", {"type": "dataset"}, True


def _get_nested(item: Dict[str, Any], field: str) -> Any:
    """Read dot-notated field value from a document."""
    current = item
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _apply_shaping(docs: List[Dict[str, Any]], payload: ObjectQueryRequest) -> List[Dict[str, Any]]:
    """Apply projection/sort/limit at API layer for backend consistency."""
    if payload.projection:
        docs = [{key: value for key, value in doc.items() if key in payload.projection} for doc in docs]
    if payload.sort:
        for sort_spec in reversed(payload.sort):
            docs = sorted(
                docs,
                key=lambda item: _get_nested(item, sort_spec.field),
                reverse=(sort_spec.order == -1),
            )
    return docs[: payload.limit]


@router.post("/{scope}", response_model=ListResponse)
def query_scope(scope: QueryScope, payload: ObjectQueryRequest, db: DBAPI = Depends(get_db_api)) -> ListResponse:
    """Run a read-only advanced query over a constrained collection scope."""
    _validate_filter_shape(payload.filter)
    collection, base_filter, include_data_supported = _get_scope_metadata(scope)
    query_filter = _merge_base_filter(base_filter=base_filter, user_filter=payload.filter)
    docs = db.query(
        collection=collection,
        filter=query_filter,
        projection=payload.projection,
        limit=payload.limit,
        sort=None if payload.sort is None else [(s.field, s.order) for s in payload.sort],
        aggregation=None if payload.aggregation is None else [(a.operator, a.field) for a in payload.aggregation],
        remove_json_unserializables=payload.remove_json_unserializables,
    )
    docs = _apply_shaping(docs=docs or [], payload=payload)
    normalized = normalize_docs(docs, include_data=(payload.include_data and include_data_supported))
    return ListResponse(items=normalized, count=len(normalized), limit=payload.limit)
