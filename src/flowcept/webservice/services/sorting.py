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
    """Sort docs ascending by the first available date field from a priority list."""
    if len(docs) <= 1:
        return docs

    chosen_field = None
    for field in date_fields:
        if any(_as_sortable_number(doc.get(field)) is not None for doc in docs):
            chosen_field = field
            break

    if chosen_field is None:
        return docs

    return sorted(
        docs,
        key=lambda doc: (
            (0, _as_sortable_number(doc.get(chosen_field)))
            if _as_sortable_number(doc.get(chosen_field)) is not None
            else (1, float("inf"))
        ),
    )
