"""
Claude Code provenance capture — install walkthrough and a simulated replay.

Claude Code delivers each lifecycle event as a JSON object on stdin to a hook
command, one process per event. Capturing a real session needs no code at all:

    /plugin marketplace add <path to this repo>      # inside Claude Code
    /plugin install flowcept

or, to wire the hooks into settings.json yourself, print them with:

    flowcept-harness install --harness claude_code

(each hook runs ``flowcept-harness hook --event <Name>``, which reads the
payload from stdin and records it).

This example replays the hook payloads a short Claude Code session would
deliver — a prompt, a tool call, a subagent, a failed tool, the answer — one
``handle()`` call per event, mimicking the one-process-per-event model. It
runs fully offline: no Claude Code and no API key. Records land as PROV-AGENT
provenance in a JSONL buffer under ``~/.flowcept/harness/buffers/``.

Run
---
    python examples/agents/claude_code/claude_code_example.py

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
    FLOWCEPT_HARNESS_CONTENT=summary  # file bodies: full, summary, or none
"""

from __future__ import annotations

import uuid

from flowcept.agents.claude_code.claude_code_plugin import handle
from flowcept.agents.harness.config import load_config


def main():
    """Replay one Claude Code session, one hook payload at a time."""
    config = load_config()
    session_id = f"claude-code-example-{uuid.uuid4().hex[:8]}"

    def fire(event: str, **fields):
        """Deliver one hook payload, shaped exactly as Claude Code sends it."""
        payload = {"hook_event_name": event, "session_id": session_id, "cwd": "/tmp/proj", **fields}
        records = handle(payload, config)
        print(f"[example] {event:<18} -> {len(records)} record(s)", flush=True)

    # Session opens.
    fire("SessionStart", source="startup", model="claude-opus-5")

    # The user asks for something: a turn begins.
    fire("UserPromptSubmit", prompt="investigate the flaky network test", prompt_id="p1")

    # The agent greps around — a tool call, Pre and Post in separate processes.
    fire("PreToolUse", tool_name="Grep", tool_use_id="t1", tool_input={"pattern": "flaky"})
    fire("PostToolUse", tool_name="Grep", tool_use_id="t1", tool_response={"matches": 3})

    # It spawns a subagent, whose tool calls land in the subagent's workflow.
    fire("PreToolUse", tool_name="Task", tool_use_id="t2", tool_input={"subagent_type": "Explore"})
    fire("SubagentStart", agent_id="a1", agent_type="Explore", task="find the failing test")
    fire("PreToolUse", tool_name="Read", tool_use_id="t3", tool_input={"file_path": "tests/test_net.py"}, agent_id="a1")
    fire("PostToolUse", tool_name="Read", tool_use_id="t3", tool_response={"lines": 120}, agent_id="a1")
    fire("SubagentStop", agent_id="a1", agent_type="Explore", last_assistant_message="tests/test_net.py:42")
    fire("PostToolUse", tool_name="Task", tool_use_id="t2", tool_response={"result": "tests/test_net.py:42"})

    # A command fails: recorded as an errored tool call, not dropped.
    fire("PreToolUse", tool_name="Bash", tool_use_id="t4", tool_input={"command": "pytest tests/test_net.py"})
    fire("PostToolUseFailure", tool_name="Bash", tool_use_id="t4", error="exit status 1")

    # The agent answers: the turn closes. Then the session closes.
    fire("Stop", last_assistant_message="It is a timing race in tests/test_net.py:42.")
    fire("SessionEnd", reason="clear")

    print(f"\n[example] Captured session {session_id!r}. Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
