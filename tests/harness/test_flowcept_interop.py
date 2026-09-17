"""The buffer must be readable by Flowcept with no conversion step.

This is the whole premise of the JSONL format choice, so it is tested against
the real library rather than a stub. Skipped when flowcept is not installed --
the capture path does not depend on it.
"""

from __future__ import annotations

import pytest

from flowcept.agents.harness.vocab import AGENT_SESSION, SUBAGENT_SESSION

from .test_claude_code import fire

flowcept = pytest.importorskip("flowcept")


@pytest.fixture
def captured_session(config):
    """A realistic session: a turn, tools, a subagent, and a failure."""
    fire(config, "SessionStart", source="startup", model="claude-opus-5")
    fire(config, "UserPromptSubmit", prompt="investigate the flaky test", prompt_id="p1")
    fire(config, "PreToolUse", tool_name="Task", tool_use_id="t1", tool_input={"subagent_type": "Explore"})
    fire(config, "SubagentStart", agent_id="a1", agent_type="Explore", task="find the test")
    fire(config, "PreToolUse", tool_name="Grep", tool_use_id="t2", tool_input={"pattern": "flaky"}, agent_id="a1")
    fire(config, "PostToolUse", tool_name="Grep", tool_use_id="t2", tool_response={"matches": 3}, agent_id="a1")
    fire(config, "SubagentStop", agent_id="a1", agent_type="Explore", last_assistant_message="tests/test_net.py")
    fire(config, "PostToolUse", tool_name="Task", tool_use_id="t1", tool_response={"result": "found"})
    fire(config, "PreToolUse", tool_name="Bash", tool_use_id="t3", tool_input={"command": "pytest"})
    fire(config, "PostToolUseFailure", tool_name="Bash", tool_use_id="t3", error="exit status 1")
    fire(config, "Stop", last_assistant_message="The flake is a timing race.")
    fire(config, "SessionEnd", reason="clear")
    return next(iter(config.buffers_dir.glob("*.jsonl")))


def test_flowcept_loads_the_buffer_without_conversion(captured_session):
    from flowcept.report.loaders import read_jsonl, split_records

    records, skipped = read_jsonl(captured_session)
    assert skipped == 0, "every line must be a record Flowcept understands"

    dataset = split_records(records)
    workflows = dataset["workflows"]
    subtypes = sorted(w.get("subtype") for w in workflows)

    # One record per workflow -- the session and its one subagent. Two records
    # for either would be counted as two separate runs.
    assert subtypes == [AGENT_SESSION, SUBAGENT_SESSION]


def test_generate_report_sees_the_right_shape(captured_session, tmp_path):
    from flowcept import Flowcept

    out = tmp_path / "card.md"
    stats = Flowcept.generate_report(
        report_type="workflow_card",
        input_jsonl_path=str(captured_session),
        format="markdown",
        output_path=str(out),
    )

    assert stats["skipped_lines"] == 0
    assert stats["n_workflows"] == 2  # session + subagent
    assert stats["n_tasks"] == 4  # turn + Task + Grep + Bash

    card = out.read_text(encoding="utf-8")
    assert "subagent:Explore" in card
    assert card.count("**Workflow ID:**") == 2


def test_an_sdk_captured_session_reports_the_same_way(config, tmp_path):
    """The in-process path must produce the same shape as the hook path."""
    from flowcept import Flowcept

    from flowcept.agents.harness import SessionTracer

    with SessionTracer("claude_agent_sdk", "s1", config=config, model="claude-opus-5") as tracer:
        tracer.prompt("fix the tests")
        ref = tracer.subagent_start("Explore", prompt="find them")
        call = tracer.tool_start("Grep", {"pattern": "def test"}, agent_ref=ref)
        tracer.tool_end(call, tool_response={"matches": 12}, agent_ref=ref)
        tracer.subagent_stop(ref, response="found 12")
        edit = tracer.tool_start("Edit", {"file_path": "a.py"})
        tracer.tool_end(edit, tool_response="ok")
        tracer.turn_end("done", usage={"input_tokens": 500})

    buffer = next(iter(config.buffers_dir.glob("*.jsonl")))
    out = tmp_path / "sdk_card.md"
    stats = Flowcept.generate_report(
        report_type="workflow_card",
        input_jsonl_path=str(buffer),
        format="markdown",
        output_path=str(out),
    )

    assert stats["skipped_lines"] == 0
    assert stats["n_workflows"] == 2  # session + subagent
    assert stats["n_tasks"] == 3  # turn + Grep + Edit
    assert "subagent:Explore" in out.read_text(encoding="utf-8")
