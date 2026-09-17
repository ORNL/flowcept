"""End-to-end tests for the Claude Code adapter.

These drive the adapter the way Claude Code does: one payload at a time,
each through :func:`~flowcept.agents.claude_code.claude_code_plugin.handle`, mimicking
the one-process-per-event model.
"""

from __future__ import annotations

import pytest

from flowcept.agents.claude_code import claude_code_plugin as claude_code
from flowcept.agents.harness.vocab import (
    AGENT_SESSION,
    AGENT_TOOL,
    AI_MODEL_INVOCATION,
    STATUS_ERROR,
    STATUS_FINISHED,
    STATUS_RUNNING,
    SUBAGENT_SESSION,
)

SESSION = "sess-abc"


def fire(config, event: str, **fields):
    """Deliver one hook payload, as Claude Code would."""
    payload = {"hook_event_name": event, "session_id": SESSION, "cwd": "/tmp/proj", **fields}
    return claude_code.handle(payload, config)


def by_type(records, kind):
    return [r for r in records if r.get("type") == kind]


def one(records, **match):
    found = [r for r in records if all(r.get(k) == v for k, v in match.items())]
    assert len(found) == 1, f"expected exactly one record matching {match}, got {len(found)}"
    return found[0]


@pytest.fixture
def session(config):
    """A started session, ready for turns."""
    fire(config, "SessionStart", source="startup", model="claude-opus-5")
    return config


# -- session lifecycle -------------------------------------------------------


def test_session_start_emits_agent_and_workflow(config, buffer_records):
    fire(config, "SessionStart", source="startup", model="claude-opus-5")
    records = buffer_records()

    agent = one(records, type="agent")
    assert agent["name"] == "claude_code:claude-opus-5"

    workflow = one(records, type="workflow")
    assert workflow["subtype"] == AGENT_SESSION
    assert workflow["status"] == STATUS_RUNNING
    assert workflow["agent_id"] == agent["agent_id"]


def test_session_opens_once_across_processes(session, buffer_records):
    """A second SessionStart (resume, or a racing hook) must not re-open."""
    fire(session, "SessionStart", source="resume", model="claude-opus-5")
    assert len(by_type(buffer_records(), "agent")) == 1


def test_session_without_id_is_dropped(config, buffer_records):
    assert claude_code.handle({"hook_event_name": "SessionStart"}, config) == []
    assert buffer_records() == []


def test_unknown_event_is_ignored(config, buffer_records):
    assert claude_code.handle({"hook_event_name": "Nonesuch", "session_id": SESSION}, config) == []
    assert buffer_records() == []


def test_session_end_supersedes_the_open_record(session, buffer_records):
    """One workflow record per workflow, or Flowcept counts it as two runs."""
    fire(session, "SessionEnd", reason="clear")

    workflows = by_type(buffer_records(), "workflow")
    assert len(workflows) == 1
    assert workflows[0]["status"] == STATUS_FINISHED
    # The closing record has to restate what the dropped one said.
    assert workflows[0]["used"]["session_id"] == SESSION
    assert workflows[0]["used"]["start_reason"] == "startup"
    assert workflows[0]["used"]["model"] == "claude-opus-5"


def test_session_records_the_harness_cwd_not_the_hooks(session, buffer_records):
    """The hook process runs wherever it likes; only the harness cwd is real."""
    fire(session, "SessionEnd", reason="clear")
    workflow = one(buffer_records(), type="workflow")
    assert workflow["used"]["cwd"] == "/tmp/proj"


# -- turns and tools ---------------------------------------------------------


def test_turn_becomes_an_ai_model_invocation(session, buffer_records):
    fire(session, "UserPromptSubmit", prompt="investigate the flaky test", prompt_id="p1")
    fire(session, "Stop", last_assistant_message="It is a timing race.")

    turn = one(buffer_records(), subtype=AI_MODEL_INVOCATION)
    assert turn["used"]["prompt"] == "investigate the flaky test"
    assert turn["generated"]["response"] == "It is a timing race."
    assert turn["status"] == STATUS_FINISHED


def test_tool_call_is_a_child_of_the_turn(session, buffer_records):
    fire(session, "UserPromptSubmit", prompt="run the tests", prompt_id="p1")
    fire(session, "PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "pytest"})
    fire(session, "PostToolUse", tool_name="Bash", tool_use_id="t1", tool_response={"exit_code": 0})
    fire(session, "Stop", last_assistant_message="green")

    records = buffer_records()
    tool = one(records, subtype=AGENT_TOOL)
    turn = one(records, subtype=AI_MODEL_INVOCATION)

    assert tool["activity_id"] == "Bash"
    assert tool["used"]["command"] == "pytest"
    assert tool["status"] == STATUS_FINISHED
    # Pre and Post run in separate processes and must agree on the task id.
    assert tool["parent_task_id"] == turn["task_id"]


def test_tool_emits_one_record_not_one_per_hook(session, buffer_records):
    fire(session, "PreToolUse", tool_name="Read", tool_use_id="t1", tool_input={"file_path": "/x"})
    fire(session, "PostToolUse", tool_name="Read", tool_use_id="t1", tool_response={"ok": True})
    assert len(by_type(buffer_records(), "task")) == 1


def test_failed_tool_is_recorded_as_error(session, buffer_records):
    fire(session, "PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "false"})
    fire(session, "PostToolUseFailure", tool_name="Bash", tool_use_id="t1", error="exit status 1")

    tool = one(buffer_records(), subtype=AGENT_TOOL)
    assert tool["status"] == STATUS_ERROR
    assert tool["stderr"] == "exit status 1"


def test_post_without_pre_still_records(session, buffer_records):
    """The Pre hook can be lost -- a crash, or capture enabled mid-session."""
    fire(session, "PostToolUse", tool_name="Glob", tool_use_id="t9", tool_response={"count": 2})
    assert one(buffer_records(), subtype=AGENT_TOOL)["activity_id"] == "Glob"


def test_new_prompt_closes_the_previous_turn(session, buffer_records):
    """No Stop arrives when the user interrupts and types again."""
    fire(session, "UserPromptSubmit", prompt="first", prompt_id="p1")
    fire(session, "UserPromptSubmit", prompt="second", prompt_id="p2")

    turns = [r for r in buffer_records() if r.get("subtype") == AI_MODEL_INVOCATION]
    assert len(turns) == 1
    assert turns[0]["used"]["prompt"] == "first"
    assert turns[0]["custom_metadata"]["close_reason"] == "superseded"


def test_open_turn_is_closed_at_session_end(session, buffer_records):
    fire(session, "UserPromptSubmit", prompt="hello", prompt_id="p1")
    fire(session, "SessionEnd", reason="clear")

    turn = one(buffer_records(), subtype=AI_MODEL_INVOCATION)
    assert turn["custom_metadata"]["close_reason"] == "session_ended"


# -- subagents ---------------------------------------------------------------


def test_subagent_becomes_a_nested_workflow(session, buffer_records):
    fire(session, "UserPromptSubmit", prompt="find it", prompt_id="p1")
    fire(session, "PreToolUse", tool_name="Task", tool_use_id="t1", tool_input={"subagent_type": "Explore"})
    fire(session, "SubagentStart", agent_id="a1", agent_type="Explore", task="find the test")
    fire(session, "PostToolUse", tool_name="Task", tool_use_id="t1", tool_response={"result": "found"})
    fire(session, "SubagentStop", agent_id="a1", agent_type="Explore", last_assistant_message="tests/test_net.py")
    fire(session, "Stop", last_assistant_message="done")

    records = buffer_records()
    parent = one(records, subtype=AGENT_SESSION)
    sub = one(records, subtype=SUBAGENT_SESSION)

    assert sub["parent_workflow_id"] == parent["workflow_id"]
    assert sub["status"] == STATUS_FINISHED
    assert sub["used"]["agent_type"] == "Explore"
    # Carried over from the superseded open record.
    assert sub["used"]["prompt"] == "find the test"
    assert sub["generated"]["response"] == "tests/test_net.py"


def test_subagent_tool_calls_land_in_the_subagent_workflow(session, buffer_records):
    fire(session, "UserPromptSubmit", prompt="find it", prompt_id="p1")
    fire(session, "PreToolUse", tool_name="Task", tool_use_id="t1", tool_input={"subagent_type": "Explore"})
    fire(session, "SubagentStart", agent_id="a1", agent_type="Explore")
    fire(session, "PreToolUse", tool_name="Grep", tool_use_id="t2", tool_input={"pattern": "flaky"}, agent_id="a1")
    fire(session, "PostToolUse", tool_name="Grep", tool_use_id="t2", tool_response={"matches": 3}, agent_id="a1")
    fire(session, "SubagentStop", agent_id="a1", agent_type="Explore")
    fire(session, "PostToolUse", tool_name="Task", tool_use_id="t1", tool_response={"result": "found"})

    records = buffer_records()
    sub = one(records, subtype=SUBAGENT_SESSION)
    grep = one(records, activity_id="Grep")
    task_tool = one(records, activity_id="Task")

    assert grep["workflow_id"] == sub["workflow_id"]
    # The Task call itself belongs to the parent -- it is what spawned the sub.
    assert task_tool["workflow_id"] == sub["parent_workflow_id"]


def test_session_counters_reflect_the_work(session, buffer_records):
    fire(session, "UserPromptSubmit", prompt="go", prompt_id="p1")
    fire(session, "PostToolUse", tool_name="Read", tool_use_id="t1", tool_response={})
    fire(session, "PostToolUseFailure", tool_name="Bash", tool_use_id="t2", error="boom")
    fire(session, "SubagentStart", agent_id="a1", agent_type="Explore")
    fire(session, "SubagentStop", agent_id="a1", agent_type="Explore")
    fire(session, "SessionEnd", reason="clear")

    generated = one(buffer_records(), subtype=AGENT_SESSION)["generated"]
    assert generated == {"turns": 1, "tool_calls": 2, "tool_errors": 1, "subagents": 1}


# -- capture safety ----------------------------------------------------------


def test_secrets_are_redacted(session, buffer_records):
    fire(
        session,
        "PostToolUse",
        tool_name="Bash",
        tool_use_id="t1",
        tool_input={"command": 'curl -H "auth: sk-ant-abcdefghij0123456789"', "api_key": "hunter2"},
        tool_response={},
    )
    blob = str(one(buffer_records(), subtype=AGENT_TOOL))
    assert "sk-ant-abcdefghij0123456789" not in blob
    assert "hunter2" not in blob
    assert "«redacted»" in blob


def test_file_bodies_are_summarized_not_stored(session, buffer_records):
    body = "\n".join(f"line {i}" for i in range(500))
    fire(
        session,
        "PostToolUse",
        tool_name="Write",
        tool_use_id="t1",
        tool_input={"file_path": "/tmp/x.py", "content": body},
        tool_response={},
    )
    content = one(buffer_records(), subtype=AGENT_TOOL)["used"]["content"]
    assert content["_summary"] is True
    assert content["lines"] == 500
    assert len(str(content)) < len(body)


def test_capture_never_raises_into_the_harness(config):
    """A malformed payload is a bug in the harness, not a reason to crash it."""
    assert claude_code.handle({"hook_event_name": "PreToolUse", "session_id": SESSION, "tool_input": object()}, config)


def test_hook_writes_nothing_to_stdout(session, capsys):
    """Stdout on UserPromptSubmit is injected into the model's context."""
    fire(session, "UserPromptSubmit", prompt="hello", prompt_id="p1")
    fire(session, "SessionEnd", reason="clear")
    captured = capsys.readouterr()
    assert captured.out == ""
