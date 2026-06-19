"""Shared pure-utility helpers for DocumentDAO implementations.

These helpers are used by both MongoDBDAO and LMDBDAO and carry no
dependency on any web-framework or schema layer.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional


from flowcept.commons.utils import to_epoch  # re-exported; defined in commons/utils.py


def get_nested(item: Dict[str, Any], field: str) -> Any:
    """Read a dot-notated field value from a document."""
    current = item
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _duration(doc: Dict[str, Any]) -> Optional[float]:
    started, ended = to_epoch(doc.get("started_at")), to_epoch(doc.get("ended_at"))
    if started is not None and ended is not None:
        return ended - started
    return None


def _metric_key(metric: Dict[str, Any]) -> str:
    """Return the canonical output key for a metric spec dict."""
    field = metric.get("field", "")
    agg = metric.get("agg", "count")
    return f"{agg}_{field}" if field else agg


def _merge_context_filter(card_filter: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """AND a card-level filter with a dashboard-level context filter."""
    if not context:
        return dict(card_filter)
    if not card_filter:
        return dict(context)
    return {"$and": [context, card_filter]}


def _merge_summary_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine per-(activity, status) rows into the task-summary response shape."""
    status_counts: Dict[str, int] = defaultdict(int)
    activities: Dict[str, Dict[str, Any]] = {}
    total = 0
    min_started, max_ended = None, None

    for row in rows:
        count = row.get("count") or 0
        total += count
        status = row.get("status") or "UNKNOWN"
        status_counts[status] += count

        activity = activities.setdefault(
            str(row.get("activity_id")),
            {
                "activity_id": row.get("activity_id"),
                "count": 0,
                "status_counts": defaultdict(int),
                "avg_duration": None,
                "min_duration": None,
                "max_duration": None,
                "sum_duration": None,
                "_weighted_sum": 0.0,
                "_weighted_count": 0,
            },
        )
        activity["count"] += count
        activity["status_counts"][status] += count
        for bound, op in (("min_duration", min), ("max_duration", max)):
            if row.get(bound) is not None:
                current = activity[bound]
                activity[bound] = row[bound] if current is None else op(current, row[bound])
        if row.get("sum_duration") is not None:
            activity["sum_duration"] = (activity["sum_duration"] or 0) + row["sum_duration"]
        if row.get("avg_duration") is not None:
            activity["_weighted_sum"] += row["avg_duration"] * count
            activity["_weighted_count"] += count

        if row.get("min_started_at") is not None:
            val = to_epoch(row["min_started_at"])
            min_started = val if min_started is None else min(min_started, val)
        if row.get("max_ended_at") is not None:
            val = to_epoch(row["max_ended_at"])
            max_ended = val if max_ended is None else max(max_ended, val)

    activity_stats = []
    for activity in activities.values():
        if activity.pop("_weighted_count"):
            activity["avg_duration"] = activity.pop("_weighted_sum") / activity["count"]
        else:
            activity.pop("_weighted_sum")
        activity["status_counts"] = dict(activity["status_counts"])
        activity_stats.append(activity)
    activity_stats.sort(key=lambda a: str(a["activity_id"]))

    return {
        "count": total,
        "status_counts": dict(status_counts),
        "activity_stats": activity_stats,
        "time_range": {"min_started_at": min_started, "max_ended_at": max_ended},
    }
