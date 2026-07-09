"""Incremental DB polling that backs the SSE live-stream endpoints.

Tasks are updated in place (status/ended_at), so the cursor advances over the max of
``registered_at``/``started_at``/``ended_at``/``utc_timestamp`` seen so far, and each
poll matches any of those fields beyond the cursor. Works on Mongo natively and on
equality-only backends (LMDB) by applying the time predicate in Python.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flowcept.flowcept_api.db_api import DBAPI

TASK_CURSOR_FIELDS = ("registered_at", "started_at", "ended_at", "utc_timestamp")
WORKFLOW_CURSOR_FIELDS = ("utc_timestamp", "created_at", "updated_at", "started_at", "ended_at")


def _supports_operators() -> bool:
    return hasattr(DBAPI.get_dao_instance(), "raw_pipeline")


def _as_epoch(value: Any) -> Optional[float]:
    """Convert numeric or datetime time values to epoch seconds (DB stores both kinds)."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, datetime):
        # Mongo returns naive UTC datetimes by default.
        return (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).timestamp()
    return None


def _doc_cursor(doc: Dict[str, Any], fields: Tuple[str, ...]) -> float:
    values = (_as_epoch(doc.get(f)) for f in fields)
    return max((v for v in values if v is not None), default=0.0)


def poll_new_docs(
    db: DBAPI,
    collection: str,
    base_filter: Dict[str, Any],
    cursor: float,
    max_batch: int,
    cursor_fields: Optional[Tuple[str, ...]] = None,
) -> Tuple[List[Dict[str, Any]], float, bool]:
    """Fetch docs newer than ``cursor`` and return ``(docs, new_cursor, truncated)``.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    collection : str
        ``tasks`` or ``workflows``.
    base_filter : dict
        Equality filter (e.g., ``{"workflow_id": ...}``); may be empty.
    cursor : float
        Epoch-seconds watermark; only docs with a time field beyond it are returned.
    max_batch : int
        Maximum docs returned per poll.
    cursor_fields : tuple of str, optional
        Time fields considered for the cursor. Defaults per collection.

    Returns
    -------
    tuple
        ``(docs, new_cursor, truncated)``.
    """
    fields = cursor_fields or (TASK_CURSOR_FIELDS if collection == "tasks" else WORKFLOW_CURSOR_FIELDS)

    if _supports_operators():
        # Time fields are floats when inserted directly and BSON dates when persisted by
        # the DocumentInserter; compare against both representations.
        cursor_dt = datetime.fromtimestamp(cursor, timezone.utc)
        time_clause = {"$or": [{f: {"$gt": cursor}} for f in fields] + [{f: {"$gt": cursor_dt}} for f in fields]}
        query_filter = {"$and": [base_filter, time_clause]} if base_filter else time_clause
        docs = db.query(collection=collection, filter=query_filter) or []
    else:
        docs = db.query(collection=collection, filter=base_filter or None) or []
        docs = [d for d in docs if _doc_cursor(d, fields) > cursor]

    seen: Dict[str, Dict[str, Any]] = {}
    id_field = "task_id" if collection == "tasks" else "workflow_id"
    for doc in docs:
        key = doc.get(id_field) or str(id(doc))
        seen[key] = doc
    deduped = sorted(seen.values(), key=lambda d: _doc_cursor(d, fields))

    truncated = len(deduped) > max_batch
    batch = deduped[:max_batch]
    new_cursor = max((_doc_cursor(d, fields) for d in batch), default=cursor)
    return batch, max(new_cursor, cursor), truncated
