"""ML model object endpoints (type=ml_model)."""

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.schemas.common import ListResponse, ObjectQueryRequest
from flowcept.webservice.services.serializers import normalize_docs

router = APIRouter(prefix="/models", tags=["models"])


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
def list_models(
    limit: int = Query(default=100, ge=1, le=1000),
    workflow_id: str | None = None,
    task_id: str | None = None,
    object_id: str | None = None,
    filter_json: str | None = None,
    include_data: bool = False,
    db: DBAPI = Depends(get_db_api),
) -> ListResponse:
    """List ML model objects with optional filters."""
    query_filter = _json_filter(filter_json)
    query_filter["type"] = "ml_model"
    if workflow_id is not None:
        query_filter["workflow_id"] = workflow_id
    if task_id is not None:
        query_filter["task_id"] = task_id
    if object_id is not None:
        query_filter["object_id"] = object_id

    docs = (db.blob_object_query(filter=query_filter) or [])[:limit]
    normalized = normalize_docs(docs, include_data=include_data)
    return ListResponse(items=normalized, count=len(normalized), limit=limit)


@router.get("/{object_id}", response_model=Dict[str, Any])
def get_model(
    object_id: str,
    version: int | None = None,
    include_data: bool = False,
    db: DBAPI = Depends(get_db_api),
):
    """Get ML model object metadata by id and optional version."""
    try:
        blob = db.get_blob_object(object_id=object_id, version=version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if blob is None or getattr(blob, "type", None) != "ml_model":
        raise HTTPException(status_code=404, detail=f"Model not found: {object_id}")

    return normalize_docs([blob.to_dict()], include_data=include_data)[0]


@router.get("/{object_id}/versions/{version}", response_model=Dict[str, Any])
def get_model_version(
    object_id: str,
    version: int,
    include_data: bool = False,
    db: DBAPI = Depends(get_db_api),
):
    """Get a specific ML model object version."""
    return get_model(object_id=object_id, version=version, include_data=include_data, db=db)


@router.get("/{object_id}/download")
def download_model(
    object_id: str,
    version: int | None = None,
    db: DBAPI = Depends(get_db_api),
):
    """Download ML model payload as a binary attachment."""
    try:
        blob = db.get_blob_object(object_id=object_id, version=version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if blob is None or getattr(blob, "type", None) != "ml_model":
        raise HTTPException(status_code=404, detail=f"Model not found: {object_id}")

    doc = blob.to_dict()
    payload = _extract_binary_or_400(doc)
    filename = f"{object_id}.bin" if version is None else f"{object_id}.v{version}.bin"
    return Response(
        content=payload,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/query", response_model=ListResponse)
def query_models(payload: ObjectQueryRequest, db: DBAPI = Depends(get_db_api)):
    """Run an advanced read-only query for ML model objects."""
    query_filter = dict(payload.filter)
    query_filter["type"] = "ml_model"
    docs = db.query(
        collection="objects",
        filter=query_filter,
        projection=payload.projection,
        limit=payload.limit,
        sort=None if payload.sort is None else [(s.field, s.order) for s in payload.sort],
        aggregation=payload.aggregation,
        remove_json_unserializables=payload.remove_json_unserializables,
    )
    docs = docs or []
    if payload.projection:
        docs = [{key: value for key, value in doc.items() if key in payload.projection} for doc in docs]
    if payload.sort:
        for sort_spec in reversed(payload.sort):
            docs = sorted(docs, key=lambda item: item.get(sort_spec.field), reverse=(sort_spec.order == -1))
    docs = docs[: payload.limit]

    normalized = normalize_docs(docs, include_data=payload.include_data)
    return ListResponse(items=normalized, count=len(normalized), limit=payload.limit)
