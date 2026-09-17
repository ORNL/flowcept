"""Deterministic identifier derivation.

Harness hooks run as independent short-lived processes: the process that sees
``PreToolUse`` is not the process that sees ``PostToolUse``. Rather than pass
IDs through a database, every ID is derived deterministically (UUIDv5) from
identifiers the harness already gives us. Two processes that see the same
``tool_use_id`` therefore compute the same ``task_id`` without coordinating.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

#: Stable namespace for all flowcept-harness identifiers. Do not change: it
#: would renumber every previously captured session.
NAMESPACE = uuid.UUID("6f3a3d2e-2b1c-5f4a-9c7e-1a2b3c4d5e6f")


def _uuid5(*parts: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "|".join(p or "" for p in parts)))


def workflow_id_for(harness: str, session_id: str) -> str:
    """Workflow ID for one harness session."""
    return _uuid5("workflow", harness, session_id)


def agent_id_for(harness: str, session_id: str, agent_name: str | None = None) -> str:
    """Agent ID for the assistant driving a session (or a named subagent)."""
    return _uuid5("agent", harness, session_id, agent_name or "main")


def turn_task_id(workflow_id: str, turn_key: str) -> str:
    """Task ID for a prompt->response turn."""
    return _uuid5("turn", workflow_id, turn_key)


def tool_task_id(workflow_id: str, tool_key: str) -> str:
    """Task ID for a single tool invocation."""
    return _uuid5("tool", workflow_id, tool_key)


def llm_task_id(workflow_id: str, call_key: str) -> str:
    """Task ID for a single model invocation."""
    return _uuid5("llm", workflow_id, call_key)


def subagent_workflow_id(parent_workflow_id: str, agent_key: str) -> str:
    """Workflow ID for a subagent, nested under its parent session."""
    return _uuid5("subworkflow", parent_workflow_id, agent_key)


def event_task_id(workflow_id: str, kind: str, key: str) -> str:
    """Task ID for a point-in-time lifecycle event (compaction, notification)."""
    return _uuid5("event", workflow_id, kind, key)


def campaign_id_for_project(project_dir: str | os.PathLike[str] | None) -> str:
    """Derive a stable campaign ID from a project directory.

    All sessions run against the same checkout land in one campaign, which is
    what makes cross-session queries ("every tool call this repo ever caused")
    possible without the user having to set anything.
    """
    if not project_dir:
        return _uuid5("campaign", "default")
    resolved = str(Path(project_dir).expanduser().resolve())
    return _uuid5("campaign", resolved)


def content_digest(text: str) -> str:
    """Short, stable digest used when file contents are summarised, not stored."""
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]
