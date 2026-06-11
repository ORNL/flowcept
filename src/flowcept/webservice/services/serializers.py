"""Serialization helpers for API responses."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Dict, List


try:
    from bson import ObjectId
except Exception:
    ObjectId = None


def _to_jsonable(value: Any, include_data: bool = False) -> Any:
    """Recursively normalize values for JSON responses."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        if include_data:
            return base64.b64encode(value).decode("ascii")
        return None
    if ObjectId is not None and isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, list):
        return [_to_jsonable(item, include_data=include_data) for item in value]
    if isinstance(value, tuple):
        return [_to_jsonable(item, include_data=include_data) for item in value]
    if isinstance(value, dict):
        return {
            str(k): _to_jsonable(v, include_data=include_data) for k, v in value.items() if include_data or k != "data"
        }
    return str(value)


def normalize_docs(docs: List[Dict[str, Any]], include_data: bool = False) -> List[Dict[str, Any]]:
    """Normalize result documents for JSON API response."""
    return [_to_jsonable(doc, include_data=include_data) for doc in docs]
