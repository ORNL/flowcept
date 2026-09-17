"""Claude Code adapter.

Claude Code delivers each lifecycle event as a JSON object on stdin to a hook
command, one process per event. This module is that command: it maps the event
onto a :class:`~flowcept.agents.harness.events.HarnessEvent` and hands it to the
recorder.

Two things shape the implementation:

*Field names are read defensively.* The hook payload is versioned with the
CLI, and only a subset of it is contractually stable across versions. Known
names are tried in order and the untouched payload is kept under
``custom_metadata.raw_event``, so a renamed field degrades the mapping rather
than losing the event.

*Nothing is ever written to stdout.* On ``UserPromptSubmit``, ``SessionStart``,
and ``UserPromptExpansion`` a hook's stdout is injected into the model's
context. A provenance hook that printed anything would silently edit the
conversation it is supposed to be observing.
"""

from __future__ import annotations

import sys
from typing import Any

from flowcept.agents.harness.config import Config
from flowcept.agents.harness.events import HarnessEvent
from flowcept.agents.harness.recorder import Recorder
from flowcept.agents.harness.runtime import log_error, project_dir_from_env, read_stdin_json, run_capture
from flowcept.agents.harness.vocab import EventKind

HARNESS = "claude_code"

#: Claude Code hook event -> normalized event kind. Events not listed here are
#: intentionally ignored: they carry no provenance we do not already capture,
#: and every extra hook is latency on the interactive path.
EVENT_MAP: dict[str, str] = {
    "SessionStart": EventKind.SESSION_START,
    "SessionEnd": EventKind.SESSION_END,
    "UserPromptSubmit": EventKind.PROMPT,
    "Stop": EventKind.TURN_END,
    "StopFailure": EventKind.TURN_END,
    "PreToolUse": EventKind.TOOL_PRE,
    "PostToolUse": EventKind.TOOL_POST,
    "PostToolUseFailure": EventKind.TOOL_ERROR,
    "SubagentStart": EventKind.SUBAGENT_START,
    "SubagentStop": EventKind.SUBAGENT_STOP,
    "Notification": EventKind.NOTIFICATION,
    "PreCompact": EventKind.COMPACT,
    "PostCompact": EventKind.COMPACT,
}


def _first(payload: dict[str, Any], *names: str) -> Any:
    """Return the first present, non-None value among ``names``."""
    for name in names:
        if name in payload and payload[name] is not None:
            return payload[name]
    return None


def _text(value: Any) -> str | None:
    """Coerce a message-ish value to text.

    ``last_assistant_message`` is usually a string but can arrive as the
    content-block list the API uses.
    """
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for block in value:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts) if parts else None
    if isinstance(value, dict):
        text = value.get("text") or value.get("content") or value.get("message")
        return text if isinstance(text, str) else None
    return str(value)


def _effort(payload: dict[str, Any]) -> str | None:
    effort = payload.get("effort")
    if isinstance(effort, dict):
        level = effort.get("level")
        return level if isinstance(level, str) else None
    return effort if isinstance(effort, str) else None


def to_event(payload: dict[str, Any]) -> HarnessEvent | None:
    """Map a Claude Code hook payload onto a normalized event."""
    hook_name = payload.get("hook_event_name")
    kind = EVENT_MAP.get(hook_name or "")
    if kind is None:
        return None

    session_id = payload.get("session_id")
    if not session_id:
        # Without a session id nothing can be correlated; drop rather than
        # invent an id that would fragment the workflow across processes.
        return None

    cwd = payload.get("cwd")

    # `agent_id` is only present when the hook fires inside a subagent. For
    # subagent lifecycle events it identifies the subagent being started or
    # stopped; for tool events it says which subagent owns the call.
    agent_ref = payload.get("agent_id")
    agent_name = payload.get("agent_type")

    # `flowcept_source_agent_id` is Flowcept's own extension key: something
    # that injects payload fields (a wrapper, a test, a future harness knob)
    # can name a framework-emitted task/agent id to link back to. It wins over
    # the FLOWCEPT_HARNESS_SOURCE_AGENT_ID env fallback read by the recorder.
    source_agent_id = payload.get("flowcept_source_agent_id")

    error = None
    if hook_name == "PostToolUseFailure":
        error = _text(_first(payload, "error", "tool_error", "tool_response")) or "tool failed"
    elif hook_name == "StopFailure":
        error = _text(_first(payload, "error", "reason", "error_type")) or "turn failed"

    event = HarnessEvent(
        kind=kind,
        harness=HARNESS,
        session_id=str(session_id),
        cwd=cwd,
        project_dir=project_dir_from_env(cwd),
        model=_first(payload, "model", "model_id"),
        permission_mode=payload.get("permission_mode"),
        effort=_effort(payload),
        source=_text(_first(payload, "source", "reason", "trigger", "notification_type")),
        prompt_id=payload.get("prompt_id"),
        prompt=_text(_first(payload, "prompt", "user_prompt")),
        response=_text(_first(payload, "last_assistant_message", "response")),
        tool_name=payload.get("tool_name"),
        tool_use_id=payload.get("tool_use_id"),
        tool_input=_first(payload, "tool_input", "tool_args"),
        tool_response=_first(payload, "tool_response", "tool_result", "tool_output"),
        error=error,
        agent_name=agent_name,
        agent_ref=agent_ref,
        source_agent_id=str(source_agent_id) if source_agent_id is not None else None,
        message=_text(payload.get("message")),
        raw=_raw_for(kind, payload),
    )

    # SubagentStart's prompt is the task the parent handed the subagent.
    if kind == EventKind.SUBAGENT_START and event.prompt is None:
        event.prompt = _text(_first(payload, "task", "description", "agent_prompt"))

    return event


def _raw_for(kind: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """Keep the raw payload only for events whose fields we do not fully model.

    Tool and turn events already have every field mapped, so storing the raw
    copy would double the size of the buffer for no query value.
    """
    if kind in (EventKind.NOTIFICATION, EventKind.COMPACT, EventKind.SESSION_END):
        return {k: v for k, v in payload.items() if k not in ("transcript_path",)}
    return None


def handle(payload: dict[str, Any], config: Config) -> list[dict[str, Any]]:
    """Record one hook payload. Returns the emitted records (for tests)."""
    event = to_event(payload)
    if event is None:
        return []
    recorder = Recorder(config, on_error=lambda msg: log_error(config, msg))
    return recorder.record(event)


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``flowcept-claude-code`` (the hook command)."""
    argv = list(sys.argv[1:] if argv is None else argv)

    def _run(config: Config) -> None:
        payload = read_stdin_json()
        # `--event NAME` lets one script serve every hook even on harness
        # versions that omit hook_event_name from the payload.
        if "--event" in argv:
            idx = argv.index("--event")
            if idx + 1 < len(argv):
                payload["hook_event_name"] = payload.get("hook_event_name") or argv[idx + 1]
        handle(payload, config)

    return run_capture(_run)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
