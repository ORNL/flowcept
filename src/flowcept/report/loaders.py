"""Data loading utilities for Flowcept reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Tuple

from flowcept.report.sanitization import sanitize_json_like


def read_jsonl(path: Path) -> Tuple[List[Dict[str, Any]], int]:
    """Read JSONL records and return ``(records, skipped_lines)``."""
    records: List[Dict[str, Any]] = []
    skipped = 0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            raw = line.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict):
                    records.append(obj)
                else:
                    skipped += 1
            except json.JSONDecodeError:
                skipped += 1
    return records, skipped


def split_records(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Split records into workflow/task/object lists.

    Returns a single-workflow dataset when all records share one ``workflow_id``,
    or a campaign dataset when multiple ``workflow_id`` values are present.
    """
    workflow_records = [r for r in records if r.get("type") == "workflow"]
    task_records = [r for r in records if r.get("type") == "task"]
    object_records = [r for r in records if r.get("object_id") is not None]

    workflow_ids = {w.get("workflow_id") for w in workflow_records if w.get("workflow_id")}

    if len(workflow_ids) <= 1:
        workflow = workflow_records[-1] if workflow_records else {}
        workflow_id = workflow.get("workflow_id")
        if workflow_id:
            task_records = [t for t in task_records if t.get("workflow_id") == workflow_id]
            object_records = [o for o in object_records if o.get("workflow_id") == workflow_id]
        return {
            "workflow": sanitize_json_like(workflow),
            "tasks": [sanitize_json_like(t) for t in task_records],
            "objects": [sanitize_json_like(strip_blob_data(o)) for o in object_records],
        }

    # Campaign: multiple workflow runs in the buffer
    campaign_id = next(
        (w.get("campaign_id") for w in workflow_records if w.get("campaign_id")),
        None,
    )
    sorted_workflows = sorted(
        workflow_records,
        key=lambda w: w.get("utc_timestamp") or 0,
    )
    return {
        "campaign_id": campaign_id,
        "workflows": [sanitize_json_like(w) for w in sorted_workflows],
        "tasks": [sanitize_json_like(t) for t in task_records],
        "objects": [sanitize_json_like(strip_blob_data(o)) for o in object_records],
    }


def strip_blob_data(obj_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return object metadata only (removing in-doc blob payload fields)."""
    filtered = dict(obj_doc)
    if "data" in filtered:
        filtered["storage_type"] = "in_object"
    elif "grid_fs_file_id" in filtered:
        filtered["storage_type"] = "gridfs"
    else:
        filtered["storage_type"] = "unknown"
    filtered.pop("data", None)
    return filtered


def load_records_from_db(workflow_id: str | None = None, campaign_id: str | None = None) -> Dict[str, Any]:
    """Load workflow/tasks/objects from DB for a workflow or campaign identifier."""
    from flowcept import Flowcept

    if not workflow_id and not campaign_id:
        raise ValueError("Either workflow_id or campaign_id must be provided for DB loading.")

    filter_obj = {"workflow_id": workflow_id} if workflow_id else {"campaign_id": campaign_id}
    workflows = Flowcept.db.query(filter=filter_obj, collection="workflows") or []
    tasks = Flowcept.db.query(filter=filter_obj, collection="tasks") or []
    objects = Flowcept.db.query(filter=filter_obj, collection="objects") or []

    workflow_ids = {w.get("workflow_id") for w in workflows if isinstance(w, dict) and w.get("workflow_id")}

    if campaign_id and len(workflow_ids) > 1:
        sorted_workflows = sorted(
            [w for w in workflows if isinstance(w, dict)],
            key=lambda w: w.get("utc_timestamp") or 0,
        )
        return {
            "campaign_id": campaign_id,
            "workflows": [sanitize_json_like(w) for w in sorted_workflows],
            "tasks": [sanitize_json_like(t) for t in tasks if isinstance(t, dict)],
            "objects": [sanitize_json_like(strip_blob_data(o)) for o in objects if isinstance(o, dict)],
        }

    workflow = workflows[-1] if workflows else {}
    return {
        "workflow": sanitize_json_like(workflow),
        "tasks": [sanitize_json_like(t) for t in tasks if isinstance(t, dict)],
        "objects": [sanitize_json_like(strip_blob_data(o)) for o in objects if isinstance(o, dict)],
    }
