"""The harness-independent event shape.

Every adapter's only job is to turn its harness's native event into one of
these. The recorder then knows nothing about Claude Code, Codex, or OTel.

Like :class:`~flowcept.agents.harness.config.Config`, this is a plain slotted class
rather than a dataclass: hooks are short-lived processes and the ``dataclasses``
import costs more than everything this module does.
"""

from __future__ import annotations

import time
from typing import Any

_FIELDS = (
    "kind",
    "harness",
    "session_id",
    "timestamp",
    "started_at",
    "cwd",
    "project_dir",
    "model",
    "permission_mode",
    "effort",
    "source",
    "prompt_id",
    "prompt",
    "response",
    "tool_name",
    "tool_use_id",
    "tool_input",
    "tool_response",
    "error",
    "call_id",
    "usage",
    "agent_name",
    "agent_ref",
    "source_agent_id",
    "raw",
    "message",
    "tags",
)


class HarnessEvent:
    """A normalized lifecycle event from some AI coding harness.

    Attributes
    ----------
    kind:
        One of :class:`flowcept.agents.harness.vocab.EventKind`.
    harness:
        Harness identifier, e.g. ``claude_code``, ``codex``, ``langgraph``.
    session_id:
        The harness's own session identifier. All provenance IDs derive from it.
    timestamp:
        When the event happened. For an event that completes something (a tool
        result, a finished turn) this is the end.
    started_at:
        When the completed work *began*, for sources that report a duration in
        one event rather than a pre/post pair -- an OTel span, or an SDK
        callback. ``None`` means the recorder should fall back to the start it
        saw earlier, or to ``timestamp``.
    source:
        Why the event fired: session start reason, end reason, compact trigger.
    agent_name:
        Subagent type/name, e.g. ``Explore``. ``None`` means the main assistant.
    agent_ref:
        The harness's own subagent identifier, used to pair start with stop.
    source_agent_id:
        A task or agent id from *another* capture system (e.g. a
        framework-emitted task that launched this session) to link back to.
        Hook adapters read it from the ``flowcept_source_agent_id`` payload
        key; ``FLOWCEPT_HARNESS_SOURCE_AGENT_ID`` is the env fallback, and the
        payload key wins.
    raw:
        The untouched source event, kept in ``custom_metadata.raw_event``.
    """

    __slots__ = _FIELDS

    def __init__(
        self,
        kind: str,
        harness: str,
        session_id: str,
        timestamp: float | None = None,
        started_at: float | None = None,
        cwd: str | None = None,
        project_dir: str | None = None,
        model: str | None = None,
        permission_mode: str | None = None,
        effort: str | None = None,
        source: str | None = None,
        prompt_id: str | None = None,
        prompt: str | None = None,
        response: str | None = None,
        tool_name: str | None = None,
        tool_use_id: str | None = None,
        tool_input: Any = None,
        tool_response: Any = None,
        error: str | None = None,
        call_id: str | None = None,
        usage: dict[str, Any] | None = None,
        agent_name: str | None = None,
        agent_ref: str | None = None,
        source_agent_id: str | None = None,
        raw: dict[str, Any] | None = None,
        message: str | None = None,
        tags: list[str] | None = None,
    ):
        self.kind = kind
        self.harness = harness
        self.session_id = session_id
        self.timestamp = time.time() if timestamp is None else timestamp
        self.started_at = started_at
        self.cwd = cwd
        self.project_dir = project_dir
        self.model = model
        self.permission_mode = permission_mode
        self.effort = effort
        self.source = source
        self.prompt_id = prompt_id
        self.prompt = prompt
        self.response = response
        self.tool_name = tool_name
        self.tool_use_id = tool_use_id
        self.tool_input = tool_input
        self.tool_response = tool_response
        self.error = error
        self.call_id = call_id
        self.usage = usage
        self.agent_name = agent_name
        self.agent_ref = agent_ref
        self.source_agent_id = source_agent_id
        self.raw = raw
        self.message = message
        self.tags = tags

    def to_dict(self) -> dict[str, Any]:
        """Return the event's non-None fields."""
        return {name: getattr(self, name) for name in _FIELDS if getattr(self, name) is not None}

    def __repr__(self) -> str:
        """Return a short debug representation naming the event and session."""
        return f"HarnessEvent(kind={self.kind!r}, harness={self.harness!r}, session_id={self.session_id!r})"
