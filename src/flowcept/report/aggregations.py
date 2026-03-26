"""Aggregation helpers for Flowcept report generation."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


def as_float(value: Any) -> Optional[float]:
    """Convert to float when possible."""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.timestamp()
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.timestamp()
        except Exception:
            pass
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def elapsed_seconds(started_at: Any, ended_at: Any) -> Optional[float]:
    """Compute elapsed seconds when both endpoints are valid."""
    start = as_float(started_at)
    end = as_float(ended_at)
    if start is None or end is None or end < start:
        return None
    return end - start


def fmt_timestamp_utc(ts: Any) -> str:
    """Format POSIX timestamp in UTC ISO-8601 format."""
    val = as_float(ts)
    if val is None:
        return "unknown"
    return datetime.fromtimestamp(val, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def group_activities(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate task rows by ``activity_id``."""
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in tasks:
        activity = str(t.get("activity_id", "unknown"))
        grouped[activity].append(t)

    rows: List[Dict[str, Any]] = []
    for activity, members in grouped.items():
        elapsed_values = [elapsed_seconds(m.get("started_at"), m.get("ended_at")) for m in members]
        elapsed_values = [v for v in elapsed_values if v is not None]
        elapsed_sorted = sorted(elapsed_values)
        elapsed_median = None
        if elapsed_sorted:
            mid = len(elapsed_sorted) // 2
            if len(elapsed_sorted) % 2 == 1:
                elapsed_median = elapsed_sorted[mid]
            else:
                elapsed_median = (elapsed_sorted[mid - 1] + elapsed_sorted[mid]) / 2.0
        status_counts = Counter(str(m.get("status", "unknown")) for m in members)
        starts = [as_float(m.get("started_at")) for m in members if as_float(m.get("started_at")) is not None]
        ends = [as_float(m.get("ended_at")) for m in members if as_float(m.get("ended_at")) is not None]
        rows.append(
            {
                "activity_id": activity,
                "n_tasks": len(members),
                "status_counts": dict(status_counts),
                "elapsed_sum": sum(elapsed_values) if elapsed_values else None,
                "elapsed_avg": (sum(elapsed_values) / len(elapsed_values)) if elapsed_values else None,
                "elapsed_median": elapsed_median,
                "elapsed_max": max(elapsed_values) if elapsed_values else None,
                "started_at_min": min(starts) if starts else None,
                "ended_at_max": max(ends) if ends else None,
            }
        )

    rows.sort(key=lambda r: r["started_at_min"] if r["started_at_min"] is not None else float("inf"))
    return rows


def group_transformations(tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Backward-compatible alias to ``group_activities``."""
    return group_activities(tasks)


def summarize_objects(objects: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    """Build metadata-only object summary for report cards."""
    by_type: Dict[str, int] = Counter()
    by_storage: Dict[str, int] = Counter()
    versions: List[int] = []
    task_linked = 0
    workflow_linked = 0
    object_sizes: List[int] = []

    for obj in objects:
        obj_type = str(obj.get("type", "unknown"))
        by_type[obj_type] += 1
        storage_type = obj.get("storage_type")
        if storage_type == "in_object":
            by_storage["in_object"] += 1
        elif storage_type == "gridfs":
            by_storage["gridfs"] += 1
        elif "grid_fs_file_id" in obj:
            by_storage["gridfs"] += 1
        elif "data" in obj:
            by_storage["in_object"] += 1
        else:
            by_storage["unknown"] += 1
        if obj.get("task_id") is not None:
            task_linked += 1
        if obj.get("workflow_id") is not None:
            workflow_linked += 1
        v = as_float(obj.get("version"))
        if v is not None:
            versions.append(int(v))
        sz = as_float(obj.get("object_size_bytes"))
        if sz is not None and sz >= 0:
            object_sizes.append(int(sz))

    return {
        "total_objects": sum(by_type.values()),
        "by_type": dict(by_type),
        "by_storage": dict(by_storage),
        "task_linked": task_linked,
        "workflow_linked": workflow_linked,
        "max_version": max(versions) if versions else None,
        "total_size_bytes": sum(object_sizes) if object_sizes else None,
        "avg_size_bytes": (sum(object_sizes) / len(object_sizes)) if object_sizes else None,
        "max_size_bytes": max(object_sizes) if object_sizes else None,
    }


def group_activities_by_workflow(tasks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Return ``{workflow_id: [activity_rows]}`` for cross-run comparisons."""
    by_workflow: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for t in tasks:
        wid = str(t.get("workflow_id", "unknown"))
        by_workflow[wid].append(t)
    return {wid: group_activities(wf_tasks) for wid, wf_tasks in by_workflow.items()}


def extract_hostnames_from_workflow(workflow: Dict[str, Any]) -> List[str]:
    """Extract unique hostnames from a workflow's ``machine_info`` dict.

    ``machine_info`` is keyed by interceptor instance id; each value may
    contain a ``hostname`` field.  Falls back to ``workflow.get('hostname')``.
    """
    hostnames: List[str] = []
    machine_info = workflow.get("machine_info")
    if isinstance(machine_info, dict):
        for entry in machine_info.values():
            if isinstance(entry, dict):
                h = entry.get("hostname")
                if h and isinstance(h, str):
                    hostnames.append(h)
    if not hostnames:
        h = workflow.get("hostname")
        if h and isinstance(h, str):
            hostnames.append(h)
    return list(dict.fromkeys(hostnames))  # deduplicate, preserve order


def workflow_bounds(tasks: List[Dict[str, Any]]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Return ``(min_start, max_end, total_elapsed)`` for task list."""
    starts = [as_float(t.get("started_at")) for t in tasks if as_float(t.get("started_at")) is not None]
    ends = [as_float(t.get("ended_at")) for t in tasks if as_float(t.get("ended_at")) is not None]
    min_start = min(starts) if starts else None
    max_end = max(ends) if ends else None
    if min_start is None or max_end is None:
        return min_start, max_end, None
    return min_start, max_end, max_end - min_start
