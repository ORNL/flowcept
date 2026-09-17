"""Builders for Flowcept-shaped provenance records.

These produce exactly the dicts Flowcept buffers internally, so they can be
inserted by the document inserter, published to the MQ, or read back by
``flowcept --generate-report`` without translation. Keys with ``None`` values
are dropped, matching ``TaskObject.to_dict``.
"""

from __future__ import annotations

import sys
import time
from typing import Any

from . import vocab
from .emit import hostname, login_name, system_name


def _clean(record: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in record.items() if v is not None}


def _env_fields() -> dict[str, Any]:
    return {
        "hostname": hostname(),
        "node_name": hostname(),
        "login_name": login_name(),
    }


def workflow_record(
    *,
    workflow_id: str,
    campaign_id: str | None = None,
    name: str | None = None,
    subtype: str = vocab.AGENT_SESSION,
    agent_id: str | None = None,
    parent_workflow_id: str | None = None,
    used: dict[str, Any] | None = None,
    generated: dict[str, Any] | None = None,
    custom_metadata: dict[str, Any] | None = None,
    started_at: float | None = None,
    ended_at: float | None = None,
    status: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Build a ``type: workflow`` record.

    Flowcept upserts workflows by ``workflow_id``, and the JSONL report loader
    keeps the last record for an id, so emitting an updated record at session
    end is the supported way to close a workflow out.
    """
    return _clean(
        {
            "type": vocab.TYPE_WORKFLOW,
            "workflow_id": workflow_id,
            "parent_workflow_id": parent_workflow_id,
            "campaign_id": campaign_id,
            "name": name,
            "subtype": subtype,
            "agent_id": agent_id,
            "adapter_id": vocab.ADAPTER_ID,
            "user": login_name(),
            "utc_timestamp": time.time(),
            "started_at": started_at,
            "ended_at": ended_at,
            "status": status,
            "workflow_description": description,
            "used": used,
            "generated": generated,
            "custom_metadata": custom_metadata,
            "environment_id": f"python{sys.version_info.major}.{sys.version_info.minor}-{system_name().lower()}",
            "sys_name": system_name(),
        }
    )


def agent_record(
    *,
    agent_id: str,
    name: str,
    workflow_id: str | None = None,
    campaign_id: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``type: agent`` record describing the assistant behind a session."""
    return _clean(
        {
            "type": vocab.TYPE_AGENT,
            "agent_id": agent_id,
            "name": name,
            "workflow_id": workflow_id,
            "campaign_id": campaign_id,
            "user": login_name(),
            "registered_at": time.time(),
            "extra_metadata": extra_metadata,
        }
    )


def task_record(
    *,
    task_id: str,
    workflow_id: str,
    activity_id: str,
    subtype: str,
    campaign_id: str | None = None,
    agent_id: str | None = None,
    source_agent_id: str | None = None,
    parent_task_id: str | None = None,
    used: dict[str, Any] | None = None,
    generated: dict[str, Any] | None = None,
    custom_metadata: dict[str, Any] | None = None,
    status: str = vocab.STATUS_FINISHED,
    started_at: float | None = None,
    ended_at: float | None = None,
    stdout: Any = None,
    stderr: Any = None,
    tags: list[str] | None = None,
    dependencies: list[str] | None = None,
    telemetry_at_start: dict[str, Any] | None = None,
    telemetry_at_end: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a ``type: task`` record."""
    now = time.time()
    return _clean(
        {
            "type": vocab.TYPE_TASK,
            "task_id": task_id,
            "workflow_id": workflow_id,
            "campaign_id": campaign_id,
            "activity_id": activity_id,
            "subtype": subtype,
            "adapter_id": vocab.ADAPTER_ID,
            "agent_id": agent_id,
            "source_agent_id": source_agent_id,
            "parent_task_id": parent_task_id,
            "used": used,
            "generated": generated,
            "custom_metadata": custom_metadata,
            "status": status,
            "started_at": started_at if started_at is not None else now,
            "ended_at": ended_at if ended_at is not None else now,
            "utc_timestamp": now,
            "stdout": stdout,
            "stderr": stderr,
            "tags": tags,
            "dependencies": dependencies,
            "telemetry_at_start": telemetry_at_start,
            "telemetry_at_end": telemetry_at_end,
            "user": login_name(),
            **_env_fields(),
        }
    )
