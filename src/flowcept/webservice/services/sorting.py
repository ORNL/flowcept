"""Sorting helpers for webservice list endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def _as_sortable_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except Exception:
            return None
    return None


def sort_docs_by_first_date_field(docs: List[Dict[str, Any]], date_fields: List[str]) -> List[Dict[str, Any]]:
    """Sort docs descending (newest first) by the first available date field from a priority list."""
    if len(docs) <= 1:
        return docs

    def first_doc_timestamp(doc: Dict[str, Any]) -> float:
        for field in date_fields:
            ts = _as_sortable_number(doc.get(field))
            if ts is not None:
                return ts
        return float("-inf")

    return sorted(
        docs,
        key=first_doc_timestamp,
        reverse=True,
    )
