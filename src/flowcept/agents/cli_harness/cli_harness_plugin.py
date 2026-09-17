"""Adapter for any harness that can run a command per lifecycle event.

Codex CLI, Gemini CLI, Cursor, OpenCode and friends all have the same shape as
Claude Code -- a JSON event handed to a hook -- but disagree on what the fields
are called. Rather than a module per harness, the differences live in declarative
JSON *profiles* under ``profiles/``:

    {
      "harness": "codex",
      "events": {"tool.start": "tool_pre"},
      "fields": {"tool_name": ["tool", "name"]}
    }

``fields`` maps a normalized :class:`~flowcept.agents.harness.events.HarnessEvent`
attribute to the source keys to try, in order. Dotted keys reach into nested
objects (``"payload.tool.name"``), so a profile can flatten a nested envelope
without any code.

Adding a harness is therefore a JSON file, and an unknown harness still works:
with no profile, the built-in default field names cover most of them, and
anything unmapped is preserved in ``custom_metadata.raw_event``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flowcept.agents.harness.config import Config
from flowcept.agents.harness.events import HarnessEvent
from flowcept.agents.harness.recorder import Recorder
from flowcept.agents.harness.runtime import log_error, project_dir_from_env
from flowcept.agents.harness.vocab import EventKind

PROFILE_DIR = Path(__file__).parent / "profiles"

#: Tried when a profile does not name a field explicitly. Ordered by how
#: common the spelling is across harnesses.
DEFAULT_FIELDS: dict[str, list[str]] = {
    "session_id": ["session_id", "sessionId", "conversation_id", "conversationId", "thread_id", "id"],
    "cwd": ["cwd", "workspace", "workingDirectory", "working_dir", "project_root"],
    "model": ["model", "model_id", "modelId", "model_name"],
    "prompt": ["prompt", "user_prompt", "userPrompt", "input", "message", "text"],
    "response": ["response", "output", "last_assistant_message", "assistant_message", "completion"],
    "tool_name": ["tool_name", "toolName", "tool", "name", "function"],
    "tool_use_id": ["tool_use_id", "toolUseId", "tool_call_id", "toolCallId", "call_id", "invocation_id"],
    "tool_input": ["tool_input", "toolInput", "arguments", "args", "params", "input"],
    "tool_response": ["tool_response", "toolResponse", "result", "output", "return_value"],
    "error": ["error", "error_message", "errorMessage", "stderr", "exception"],
    "agent_name": ["agent_type", "agentType", "agent_name", "subagent_type", "role"],
    "agent_ref": ["agent_id", "agentId", "subagent_id", "child_session_id"],
    # Flowcept's own extension key: a framework-emitted task/agent id to link
    # back to. Wins over the FLOWCEPT_HARNESS_SOURCE_AGENT_ID env fallback.
    "source_agent_id": ["flowcept_source_agent_id"],
    "prompt_id": ["prompt_id", "promptId", "turn_id", "turnId", "message_id"],
    "source": ["source", "reason", "trigger", "event_reason"],
    "permission_mode": ["permission_mode", "permissionMode", "approval_mode", "mode"],
    "effort": ["effort", "reasoning_effort", "reasoningEffort"],
    "message": ["message", "notification", "text"],
    "call_id": ["request_id", "requestId", "response_id", "generation_id"],
    "usage": ["usage", "token_usage", "tokenUsage", "tokens"],
}

#: Event names seen in the wild, mapped onto normalized kinds. Matching is
#: case-insensitive and ignores separators, so ``PreToolUse``, ``pre_tool_use``
#: and ``tool.before`` all land in the same place.
DEFAULT_EVENTS: dict[str, str] = {
    "sessionstart": EventKind.SESSION_START,
    "sessionbegin": EventKind.SESSION_START,
    "start": EventKind.SESSION_START,
    "sessionend": EventKind.SESSION_END,
    "sessionstop": EventKind.SESSION_END,
    "stop": EventKind.TURN_END,
    "userpromptsubmit": EventKind.PROMPT,
    "prompt": EventKind.PROMPT,
    "userinput": EventKind.PROMPT,
    "turnstart": EventKind.PROMPT,
    "turnend": EventKind.TURN_END,
    "responsecomplete": EventKind.TURN_END,
    "agentmessage": EventKind.TURN_END,
    "pretooluse": EventKind.TOOL_PRE,
    "toolstart": EventKind.TOOL_PRE,
    "toolbefore": EventKind.TOOL_PRE,
    "toolcall": EventKind.TOOL_PRE,
    "posttooluse": EventKind.TOOL_POST,
    "toolend": EventKind.TOOL_POST,
    "toolafter": EventKind.TOOL_POST,
    "toolresult": EventKind.TOOL_POST,
    "tooldone": EventKind.TOOL_POST,
    "toolerror": EventKind.TOOL_ERROR,
    "toolfailed": EventKind.TOOL_ERROR,
    "posttoolusefailure": EventKind.TOOL_ERROR,
    "subagentstart": EventKind.SUBAGENT_START,
    "agentstart": EventKind.SUBAGENT_START,
    "subagentstop": EventKind.SUBAGENT_STOP,
    "agentstop": EventKind.SUBAGENT_STOP,
    "llmcall": EventKind.LLM_CALL,
    "modelcall": EventKind.LLM_CALL,
    "inference": EventKind.LLM_CALL,
    "notification": EventKind.NOTIFICATION,
    "precompact": EventKind.COMPACT,
    "postcompact": EventKind.COMPACT,
    "compact": EventKind.COMPACT,
}


def _normalize_event_name(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


class Profile:
    """A harness's field and event naming, loaded from JSON."""

    __slots__ = ("constants", "events", "fields", "harness")

    def __init__(self, harness: str, events=None, fields=None, constants=None):
        self.harness = harness
        self.events = {_normalize_event_name(k): v for k, v in (events or {}).items()}
        self.fields = fields or {}
        self.constants = constants or {}

    @classmethod
    def load(cls, name: str | None, harness: str) -> Profile:
        """Load a profile by name or path, falling back to the defaults."""
        if not name:
            candidate = PROFILE_DIR / f"{harness}.json"
            if not candidate.is_file():
                return cls(harness)
        else:
            candidate = Path(name)
            if not candidate.is_file():
                candidate = PROFILE_DIR / f"{name}.json"
            if not candidate.is_file():
                return cls(harness)
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls(harness)
        return cls(
            harness=data.get("harness") or harness,
            events=data.get("events"),
            fields=data.get("fields"),
            constants=data.get("constants"),
        )

    def kind_for(self, event_name: str) -> str | None:
        """Return the event kind mapped to *event_name*, or None if unmapped."""
        key = _normalize_event_name(event_name)
        return self.events.get(key) or DEFAULT_EVENTS.get(key)

    def keys_for(self, field: str) -> list[str]:
        """Return the payload keys to try when extracting *field*."""
        configured = self.fields.get(field)
        if configured is None:
            return DEFAULT_FIELDS.get(field, [field])
        if isinstance(configured, str):
            return [configured]
        return list(configured)


def _dig(payload: dict[str, Any], key: str) -> Any:
    """Look up ``key``, descending through dots into nested objects.

    A numeric segment indexes a list, so ``workspace_roots.0`` reaches the
    first element of a list-valued key.
    """
    if "." not in key:
        return payload.get(key)
    current: Any = payload
    for part in key.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, (list, tuple)) and part.lstrip("-").isdigit():
            index = int(part)
            current = current[index] if -len(current) <= index < len(current) else None
        else:
            return None
        if current is None:
            return None
    return current


def _pick(payload: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = _dig(payload, key)
        if value is not None:
            return value
    return None


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        parts = [p for p in (_as_text(v) for v in value) if p]
        return "\n".join(parts) if parts else None
    if isinstance(value, dict):
        for key in ("text", "content", "message", "value"):
            if isinstance(value.get(key), str):
                return value[key]
        return None
    return str(value)


def _event_name(payload: dict[str, Any], explicit: str | None) -> str | None:
    if explicit:
        return explicit
    for key in ("hook_event_name", "event", "event_name", "eventName", "type", "kind", "phase"):
        value = payload.get(key)
        if isinstance(value, str):
            return value
    return None


def to_event(
    payload: dict[str, Any],
    *,
    harness: str,
    profile: Profile,
    event: str | None = None,
) -> HarnessEvent | None:
    """Map an arbitrary harness payload onto a normalized event."""
    name = _event_name(payload, event)
    if not name:
        return None
    kind = profile.kind_for(name)
    if kind is None:
        return None

    session_id = _as_text(_pick(payload, profile.keys_for("session_id")))
    if not session_id:
        return None

    cwd = _as_text(_pick(payload, profile.keys_for("cwd")))
    usage = _pick(payload, profile.keys_for("usage"))

    normalized = HarnessEvent(
        kind=kind,
        harness=profile.harness or harness,
        session_id=session_id,
        cwd=cwd,
        project_dir=project_dir_from_env(cwd),
        model=_as_text(_pick(payload, profile.keys_for("model"))),
        permission_mode=_as_text(_pick(payload, profile.keys_for("permission_mode"))),
        effort=_as_text(_pick(payload, profile.keys_for("effort"))),
        source=_as_text(_pick(payload, profile.keys_for("source"))),
        prompt_id=_as_text(_pick(payload, profile.keys_for("prompt_id"))),
        error=_as_text(_pick(payload, profile.keys_for("error"))),
        call_id=_as_text(_pick(payload, profile.keys_for("call_id"))),
        usage=usage if isinstance(usage, dict) else None,
        agent_name=_as_text(_pick(payload, profile.keys_for("agent_name"))),
        agent_ref=_as_text(_pick(payload, profile.keys_for("agent_ref"))),
        source_agent_id=_as_text(_pick(payload, profile.keys_for("source_agent_id"))),
        message=_as_text(_pick(payload, profile.keys_for("message"))),
        # Only lifecycle events keep their raw payload (the recorder discards it
        # otherwise). Tool and turn events are high-volume and would double the
        # buffer; their fields are the ones profiles exist to map anyway.
        raw=payload if kind in (EventKind.NOTIFICATION, EventKind.COMPACT, EventKind.SESSION_END) else None,
    )

    # Prompt and tool fields share source keys across harnesses ("input" is a
    # prompt on a turn event and arguments on a tool event), so they are only
    # read for the events where they mean what we want.
    if kind in (EventKind.PROMPT, EventKind.TURN_END, EventKind.LLM_CALL, EventKind.SUBAGENT_START):
        normalized.prompt = _as_text(_pick(payload, profile.keys_for("prompt")))
    if kind in (EventKind.TURN_END, EventKind.LLM_CALL, EventKind.SUBAGENT_STOP):
        normalized.response = _as_text(_pick(payload, profile.keys_for("response")))
    if kind in (EventKind.TOOL_PRE, EventKind.TOOL_POST, EventKind.TOOL_ERROR):
        normalized.tool_name = _as_text(_pick(payload, profile.keys_for("tool_name")))
        normalized.tool_use_id = _as_text(_pick(payload, profile.keys_for("tool_use_id")))
        normalized.tool_input = _pick(payload, profile.keys_for("tool_input"))
        normalized.tool_response = _pick(payload, profile.keys_for("tool_response"))

    for key, value in profile.constants.items():
        if hasattr(normalized, key):
            setattr(normalized, key, value)

    return normalized


def handle(
    payload: dict[str, Any],
    config: Config,
    *,
    harness: str = "generic",
    profile: str | None = None,
    event: str | None = None,
) -> list[dict[str, Any]]:
    """Record one payload from an arbitrary harness."""
    loaded = Profile.load(profile, harness)
    normalized = to_event(payload, harness=harness, profile=loaded, event=event)
    if normalized is None:
        return []
    recorder = Recorder(config, on_error=lambda msg: log_error(config, msg))
    return recorder.record(normalized)
