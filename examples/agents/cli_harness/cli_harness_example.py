"""
Generic CLI-harness provenance capture through the profile-driven adapter.

Codex CLI, Gemini CLI, Cursor, OpenCode and friends all have the same shape as
Claude Code — a JSON event handed to a hook command — but disagree on what the
fields are called. The differences live in JSON *profiles* under
``src/flowcept/agents/cli_harness/profiles/``; adding a harness means adding a
file, not writing code.

In production the harness's hook is pointed at:

    flowcept-harness hook --harness codex --profile codex

This example is a Python driver that simulates that flow: it replays the hook
payloads a Codex-style session would deliver — one ``handle()`` call per
event, mimicking the one-process-per-event model — using the field names the
bundled ``codex`` profile maps. It runs fully offline, no harness and no API
key. Records land as PROV-AGENT provenance in a JSONL buffer under
``~/.flowcept/harness/buffers/``.

Run
---
    python examples/agents/cli_harness/cli_harness_example.py

Then inspect the capture:

    flowcept-harness sessions
    flowcept-harness show
    flowcept-harness report

Plugin configuration
--------------------
The harness plugins are configured with environment variables, not
settings.yaml (see src/flowcept/agents/harness/README.md for the full table):

    FLOWCEPT_HARNESS_ENABLED=1        # master switch (default)
    FLOWCEPT_HARNESS_ONLINE=0         # 1 publishes to a live Flowcept backend
    FLOWCEPT_HARNESS_REDACT=1         # redact credential-shaped values

``flowcept-harness install --harness codex`` prints the hook command to wire
into the real harness.
"""

from __future__ import annotations

import uuid

from flowcept.agents.cli_harness.cli_harness_plugin import handle
from flowcept.agents.harness.config import load_config


def main():
    """Replay one Codex-style session, one hook payload at a time."""
    config = load_config()
    session_id = f"codex-example-{uuid.uuid4().hex[:8]}"

    # Each payload uses Codex's own event and field names; the `codex` profile
    # maps them onto the normalized HarnessEvent. The event name is read from
    # the payload's "type" key, exactly as a typed notification envelope
    # delivers it.
    events = [
        # Session opens.
        {"type": "session-configured", "session_id": session_id, "cwd": "/tmp/proj", "model": "gpt-5"},
        # The user asks for something: a turn begins.
        {"type": "user-message", "session_id": session_id, "message": "run the unit tests"},
        # The agent runs a command: a tool call, begin and end.
        {
            "type": "exec-command-begin",
            "session_id": session_id,
            "call_id": "call-1",
            "command": "pytest -q tests/unit",
        },
        {
            "type": "exec-command-end",
            "session_id": session_id,
            "call_id": "call-1",
            "stdout": "42 passed in 3.14s",
        },
        # The agent answers: the turn closes.
        {
            "type": "agent-turn-complete",
            "session_id": session_id,
            "last_agent_message": "All 42 unit tests pass.",
        },
        # Session closes.
        {"type": "session-end", "session_id": session_id},
    ]

    total = 0
    for payload in events:
        records = handle(payload, config, harness="codex", profile="codex")
        total += len(records)
        print(f"[example] {payload['type']:<22} -> {len(records)} record(s)", flush=True)

    print(f"\n[example] Captured session {session_id!r} ({total} records). Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
