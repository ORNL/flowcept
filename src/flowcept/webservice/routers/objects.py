"""Blob object endpoints."""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse, ObjectQueryRequest
from flowcept.webservice.services.serializers import normalize_docs
from flowcept.webservice.services.sorting import sort_docs_by_first_date_field

router = APIRouter(prefix="/objects", tags=["objects"])


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


def _extract_binary_or_400(doc: Dict[str, Any]) -> bytes:
    payload = doc.get("data")
    if payload is None:
        raise HTTPException(status_code=404, detail="Object payload not available.")
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    raise HTTPException(status_code=400, detail=f"Unsupported payload type for download: {type(payload).__name__}")


@router.get("", response_model=ListResponse)
def list_objects(
    limit: int = Query(default=100, ge=1, le=1000),
    object_id: str | None = None,
    workflow_id: str | None = None,
    task_id: str | None = None,
    type: str | None = None,
    filter_json: str | None = None,
    include_data: bool = False,
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List objects with optional basic filters."""
    query_filter = _json_filter(filter_json)
    if object_id is not None:
        query_filter["object_id"] = object_id
    if workflow_id is not None:
        query_filter["workflow_id"] = workflow_id
    if task_id is not None:
        query_filter["task_id"] = task_id
    if type is not None:
        query_filter["type"] = type

    docs = db.blob_object_query(filter=query_filter) or []
    docs = sort_docs_by_first_date_field(docs, ["created_at", "updated_at", "utc_timestamp", "timestamp"])
    docs = docs[:limit]
    normalized = normalize_docs(docs, include_data=include_data)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.get("/{object_id}", response_model=Dict[str, Any])
def get_object(object_id: str, include_data: bool = False, db: DBAPI = Depends(get_db_api)) -> Dict[str, Any]:
    """Get latest version of an object by id."""
    try:
        obj = db.get_blob_object(object_id=object_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if obj is None:
        raise HTTPException(status_code=404, detail=f"Object not found: {object_id}")

    normalized = normalize_docs([obj.to_dict()], include_data=include_data)
    return normalized[0]


@router.get("/{object_id}/versions/{version}", response_model=Dict[str, Any])
def get_object_version(
    object_id: str,
    version: int,
    include_data: bool = False,
    db: DBAPI = Depends(get_db_api),
) -> Dict[str, Any]:
    """Get a specific object version by id and version number."""
    try:
        obj = db.get_blob_object(object_id=object_id, version=version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if obj is None:
        raise HTTPException(status_code=404, detail=f"Object not found: {object_id}, version={version}")

    normalized = normalize_docs([obj.to_dict()], include_data=include_data)
    return normalized[0]


@router.get("/{object_id}/download")
def download_object(
    object_id: str,
    version: int | None = None,
    db: DBAPI = Depends(get_db_api),
) -> Response:
    """Download object payload as binary."""
    try:
        obj = db.get_blob_object(object_id=object_id, version=version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if obj is None:
        raise HTTPException(status_code=404, detail=f"Object not found: {object_id}")

    payload = _extract_binary_or_400(obj.to_dict())
    filename = f"{object_id}.bin" if version is None else f"{object_id}.v{version}.bin"
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{object_id}/versions/{version}/download")
def download_object_version(
    object_id: str,
    version: int,
    db: DBAPI = Depends(get_db_api),
) -> Response:
    """Download a specific object payload version as binary."""
    return download_object(object_id=object_id, version=version, db=db)


@router.get("/{object_id}/history", response_model=ListResponse)
def get_object_history(
    object_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """Get object metadata history (latest-first)."""
    try:
        history = db.get_object_history(object_id) or []
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    history = history[:limit]
    normalized = normalize_docs(history)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.post("/query", response_model=ListResponse)
def query_objects(payload: ObjectQueryRequest, db: DBAPI = Depends(get_db_api)) -> ListResponse:
    """Run an advanced read-only object query."""
    docs = db.query(
        collection="objects",
        filter=payload.filter,
        projection=payload.projection,
        limit=payload.limit,
        sort=None if payload.sort is None else [(s.field, s.order) for s in payload.sort],
        aggregation=payload.aggregation,
        remove_json_unserializables=payload.remove_json_unserializables,
    )
    docs = docs or []

    # Mongo object_query currently ignores projection/sort/limit. Apply API-level shaping here.
    if payload.projection:
        docs = [{key: value for key, value in doc.items() if key in payload.projection} for doc in docs]
    if payload.sort:
        for sort_spec in reversed(payload.sort):
            docs = sorted(
                docs,
                key=lambda item: item.get(sort_spec.field),
                reverse=(sort_spec.order == -1),
            )
    docs = docs[: payload.limit]

    normalized = normalize_docs(docs, include_data=payload.include_data)
    return ListResponse(items=normalized, count=len(normalized), limit=payload.limit)
