"""Tests for the profile-driven adapter used by non-Claude-Code harnesses."""

from __future__ import annotations

import json

import pytest

from flowcept.agents.cli_harness import cli_harness_plugin as generic
from flowcept.agents.cli_harness.cli_harness_plugin import PROFILE_DIR, Profile, _dig, to_event
from flowcept.agents.harness.vocab import AGENT_TOOL, AI_MODEL_INVOCATION, EventKind


def test_dig_walks_dicts_and_lists():
    """_dig descends dotted paths through dicts and list indices."""
    payload = {"a": {"b": [{"c": 1}]}}
    assert _dig(payload, "a.b.0.c") == 1
    assert _dig(payload, "a.b.9.c") is None
    assert _dig(payload, "a.missing.c") is None


def test_event_names_match_regardless_of_spelling():
    """Event-name matching ignores case and separators."""
    profile = Profile("x")
    for spelling in ("PreToolUse", "pre_tool_use", "pre-tool-use", "tool.before"):
        assert profile.kind_for(spelling) == EventKind.TOOL_PRE, spelling


def test_unknown_harness_works_without_a_profile(config, buffer_records):
    """Default field names should carry a harness nobody has written up yet."""
    generic.handle(
        {"event": "session_start", "session_id": "s1", "cwd": "/w", "model": "gpt-5"},
        config,
        harness="mystery",
    )
    generic.handle(
        {
            "event": "tool_end",
            "session_id": "s1",
            "toolName": "shell",
            "toolCallId": "c1",
            "arguments": {"cmd": "ls"},
            "result": {"ok": True},
        },
        config,
        harness="mystery",
    )

    tool = next(r for r in buffer_records() if r.get("subtype") == AGENT_TOOL)
    assert tool["activity_id"] == "shell"
    assert tool["used"]["cmd"] == "ls"
    assert tool["custom_metadata"]["harness"] == "mystery"


def test_unmapped_event_is_ignored(config, buffer_records):
    """An event name mapped to no kind produces no records."""
    assert generic.handle({"event": "heartbeat", "session_id": "s1"}, config) == []
    assert buffer_records() == []


def test_missing_event_name_is_ignored(config):
    """A payload with no recognizable event-name key produces no records."""
    assert generic.handle({"session_id": "s1"}, config) == []


@pytest.mark.parametrize("name", ["codex", "gemini", "cursor", "opencode"])
def test_shipped_profiles_are_valid(name):
    """Every shipped profile maps its events onto kinds the recorder handles."""
    data = json.loads((PROFILE_DIR / f"{name}.json").read_text(encoding="utf-8"))
    assert data["harness"]
    assert data["events"], "a profile with no event map adds nothing"

    profile = Profile.load(name, name)
    # Every declared event must resolve to a kind the recorder handles.
    for source_name, kind in data["events"].items():
        assert kind in EventKind.ALL, f"{name}: {source_name} -> unknown kind {kind}"
        assert profile.kind_for(source_name) == kind


def test_profile_falls_back_when_file_is_missing():
    """A missing profile file falls back to the built-in defaults."""
    profile = Profile.load("no-such-profile", "somewhere")
    assert profile.harness == "somewhere"
    assert profile.kind_for("SessionStart") == EventKind.SESSION_START


def test_codex_nested_fields(config, buffer_records):
    """The codex profile digs tool detail out of the nested invocation object."""
    generic.handle({"event": "session-start", "session_id": "c1", "cwd": "/repo"}, config, harness="codex")
    generic.handle(
        {
            "event": "mcp-tool-call-end",
            "session_id": "c1",
            "call_id": "call-1",
            "invocation": {"tool": "fetch", "arguments": {"url": "https://x"}},
            "output": {"status": 200},
        },
        config,
        harness="codex",
    )

    tool = next(r for r in buffer_records() if r.get("subtype") == AGENT_TOOL)
    assert tool["activity_id"] == "fetch"
    assert tool["used"]["url"] == "https://x"
    assert tool["generated"]["status"] == 200


def test_opencode_dotted_paths(config, buffer_records):
    """The opencode profile resolves dotted paths like properties.info.id."""
    generic.handle(
        {"type": "session.created", "properties": {"info": {"id": "o1"}}, "directory": "/repo"},
        config,
        harness="opencode",
    )
    generic.handle(
        {
            "type": "tool.execute.after",
            "sessionID": "o1",
            "tool": "edit",
            "callID": "k1",
            "args": {"file": "a.py"},
            "output": "done",
        },
        config,
        harness="opencode",
    )

    records = buffer_records()
    assert next(r for r in records if r.get("subtype") == AGENT_TOOL)["activity_id"] == "edit"


def test_cursor_workspace_root_is_indexed(config, buffer_records):
    """The cursor profile indexes the first entry of workspace_roots as cwd."""
    generic.handle(
        {
            "hook_event_name": "start",
            "conversation_id": "x1",
            "workspace_roots": ["/home/me/repo", "/other"],
        },
        config,
        harness="cursor",
    )
    workflow = next(r for r in buffer_records() if r.get("type") == "workflow")
    assert workflow["used"]["cwd"] == "/home/me/repo"


def test_gemini_camelcase_session_fields(config, buffer_records):
    """The gemini profile reads camelCase keys and renames the harness to gemini_cli."""
    generic.handle(
        {
            "event": "SessionStart",
            "sessionId": "g1",
            "workspaceDir": "/repo",
            "model": "gemini-2.5-pro",
        },
        config,
        harness="gemini",
    )
    workflow = next(r for r in buffer_records() if r.get("type") == "workflow")
    assert workflow["used"]["cwd"] == "/repo"
    assert workflow["used"]["model"] == "gemini-2.5-pro"
    assert workflow["custom_metadata"]["harness"] == "gemini_cli"


def test_gemini_nested_toolcall_object(config, buffer_records):
    """Tool detail nested under gemini's toolCall object lands on one tool task."""
    generic.handle({"event": "SessionStart", "sessionId": "g1"}, config, harness="gemini")
    generic.handle(
        {
            "event": "BeforeToolCall",
            "sessionId": "g1",
            "toolCall": {"name": "run_shell_command", "callId": "t1", "args": {"command": "ls"}},
        },
        config,
        harness="gemini",
    )
    generic.handle(
        {
            "event": "AfterToolCall",
            "sessionId": "g1",
            "toolCall": {"name": "run_shell_command", "callId": "t1", "response": {"exit_code": 0}},
        },
        config,
        harness="gemini",
    )

    tools = [r for r in buffer_records() if r.get("subtype") == AGENT_TOOL]
    assert len(tools) == 1  # the pre/post pair pairs up on toolCall.callId
    assert tools[0]["activity_id"] == "run_shell_command"
    assert tools[0]["used"]["command"] == "ls"
    assert tools[0]["generated"]["exit_code"] == 0
    assert tools[0]["custom_metadata"]["duration_known"] is True


def test_gemini_prompt_and_model_response_form_a_turn(config, buffer_records):
    """UserPromptSubmit opens a turn that ModelResponse closes with the answer."""
    generic.handle({"event": "SessionStart", "sessionId": "g1"}, config, harness="gemini")
    generic.handle({"event": "UserPromptSubmit", "sessionId": "g1", "prompt": "refactor"}, config, harness="gemini")
    generic.handle({"event": "ModelResponse", "sessionId": "g1", "responseText": "done"}, config, harness="gemini")

    turn = next(r for r in buffer_records() if r.get("subtype") == AI_MODEL_INVOCATION)
    assert turn["used"]["prompt"] == "refactor"
    assert turn["generated"]["response"] == "done"
    assert turn["custom_metadata"]["harness"] == "gemini_cli"


def test_gemini_tool_error_is_a_failed_task(config, buffer_records):
    """ToolCallError becomes an ERROR task with the nested toolCall.error as stderr."""
    generic.handle({"event": "SessionStart", "sessionId": "g1"}, config, harness="gemini")
    generic.handle(
        {
            "event": "ToolCallError",
            "sessionId": "g1",
            "toolCall": {"name": "write_file", "callId": "t9", "error": "permission denied"},
        },
        config,
        harness="gemini",
    )

    tool = next(r for r in buffer_records() if r.get("subtype") == AGENT_TOOL)
    assert tool["activity_id"] == "write_file"
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "permission denied"


def test_prompt_and_tool_fields_do_not_collide(config):
    """`input` means a prompt on a turn and arguments on a tool call."""
    profile = Profile("x")
    prompt_event = to_event(
        {"event": "prompt", "session_id": "s", "input": "do the thing"},
        harness="x",
        profile=profile,
    )
    tool_event = to_event(
        {"event": "tool_start", "session_id": "s", "name": "grep", "input": {"pattern": "x"}},
        harness="x",
        profile=profile,
    )
    assert prompt_event.prompt == "do the thing"
    assert prompt_event.tool_input is None
    assert tool_event.tool_input == {"pattern": "x"}
    assert tool_event.prompt is None


def test_generic_turn_is_recorded(config, buffer_records):
    """A prompt/turn_end pair from an unprofiled harness becomes one turn task."""
    generic.handle({"event": "session_start", "session_id": "s1"}, config, harness="h")
    generic.handle({"event": "prompt", "session_id": "s1", "prompt": "hi"}, config, harness="h")
    generic.handle({"event": "turn_end", "session_id": "s1", "response": "hello"}, config, harness="h")

    turn = next(r for r in buffer_records() if r.get("subtype") == AI_MODEL_INVOCATION)
    assert turn["used"]["prompt"] == "hi"
    assert turn["generated"]["response"] == "hello"
