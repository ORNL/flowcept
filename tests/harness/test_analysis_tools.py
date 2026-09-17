"""Tests for the provenance analysis tools on the harness MCP server and CLI.

The MCP tools are exercised through the server's own registry (like
``test_mcp_server.py``) against a captured synthetic session; the CLI
``analyze`` subcommand is driven like ``test_cli.py`` does.  Everything runs
offline: no MQ, MongoDB, network, or LLM keys.
"""

from __future__ import annotations

import json

import pytest

from flowcept.agents.harness import cli, ids

from .test_claude_code import SESSION, fire
from .test_mcp_server import call

pytest.importorskip("mcp")

from flowcept.agents.harness import mcp_server  # noqa: E402


def record_session(config):
    """Capture one synthetic session with a failure and a subagent."""
    fire(config, "SessionStart", source="startup", model="claude-opus-5")
    fire(config, "UserPromptSubmit", prompt="fix the flake", prompt_id="p1")
    fire(config, "PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "pytest -q"})
    fire(config, "PostToolUse", tool_name="Bash", tool_use_id="t1", tool_response={"exit_code": 0})
    fire(config, "PreToolUse", tool_name="Bash", tool_use_id="t2", tool_input={"command": "ruff check"})
    fire(config, "PostToolUseFailure", tool_name="Bash", tool_use_id="t2", error="1 error found")
    fire(config, "SubagentStart", agent_id="a1", agent_type="Explore")
    fire(config, "PreToolUse", tool_name="Grep", tool_use_id="t3", tool_input={"pattern": "flaky"}, agent_id="a1")
    fire(config, "PostToolUse", tool_name="Grep", tool_use_id="t3", tool_response={"matches": 2}, agent_id="a1")
    fire(config, "SubagentStop", agent_id="a1", agent_type="Explore")
    fire(config, "Stop", last_assistant_message="Fixed the race.")
    fire(config, "SessionEnd", reason="clear")


@pytest.fixture
def server(config):
    """Build an MCP server over one captured synthetic session."""
    record_session(config)
    return mcp_server.build_server(config)


def test_analysis_tools_are_registered(server):
    """The four analysis tools are registered on the harness server."""
    names = {t.name for t in server._tool_manager.list_tools()}
    assert {"analyze_session", "analyze_errors", "find_slowest", "cross_links"} <= names


def test_analysis_tools_have_descriptions(server):
    """Every analysis tool carries a description for the model."""
    for name in ("analyze_session", "analyze_errors", "find_slowest", "cross_links"):
        tool = server._tool_manager.get_tool(name)
        assert tool.description


def test_analyze_session_summary_and_behavior(server):
    """analyze_session returns a summary plus agent behavior."""
    result = call(server, "analyze_session")
    summary = result["summary"]
    assert summary["n_workflows"] == 2
    assert summary["tasks_by_activity"]["Bash"] == 2
    assert summary["status_counts"]["ERROR"] == 1
    behavior = result["agent_behavior"]
    assert behavior["n_subagent_sessions"] == 1
    assert behavior["sessions"][0]["n_subagents"] == 1
    tools_seen = {tool for entry in behavior["agents"].values() for tool in entry["tool_calls_by_tool"]}
    assert {"Bash", "Grep"} <= tools_seen


def test_analyze_session_reports_a_miss(server):
    """An unknown session id returns an error payload."""
    assert "error" in call(server, "analyze_session", session="nope")


def test_analyze_errors_tool(server):
    """analyze_errors reports per-activity failures with excerpts."""
    errors = call(server, "analyze_errors")
    assert errors["n_failed"] == 1
    assert errors["by_activity"]["Bash"]["excerpts"] == ["1 error found"]
    assert errors["by_activity"]["Bash"]["error_rate"] == pytest.approx(0.5)


def test_analyze_errors_reports_a_miss(server):
    """An unknown session id returns an error payload."""
    assert "error" in call(server, "analyze_errors", session="nope")


def test_find_slowest_tool(server):
    """find_slowest returns ordered rows with the expected fields."""
    rows = call(server, "find_slowest", limit=2)
    assert len(rows) == 2
    assert rows[0]["elapsed_seconds"] >= rows[1]["elapsed_seconds"]
    assert {"task_id", "activity_id", "status", "parent_depth"} <= set(rows[0])


def test_cross_links_tool_finds_a_planted_link(config):
    """A planted plugin record linking a harness task is surfaced."""
    record_session(config)
    # Plant a framework-plugin task linking back to a harness tool task.
    buffer = next(iter(config.buffers_dir.glob("*.jsonl")))
    records = [json.loads(line) for line in buffer.read_text().splitlines() if line.strip()]
    tool_task = next(r for r in records if r.get("subtype") == "agent_tool")
    linked = {
        "task_id": "lg-1",
        "workflow_id": "wf-lg",
        "activity_id": "graph",
        "subtype": "langgraph_graph",
        "status": "FINISHED",
        "custom_metadata": {"source_agent_id": tool_task["task_id"]},
    }
    with buffer.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(linked) + "\n")

    server = mcp_server.build_server(config)
    result = call(server, "cross_links")
    assert result["n_links"] == 1
    link = result["links"][0]
    assert link["source_task_id"] == tool_task["task_id"]
    assert link["target_task_id"] == "lg-1"
    assert "langgraph" in link["frameworks"]


def test_cross_links_without_links(server):
    """A plain session reports zero links and unlinked tasks."""
    result = call(server, "cross_links")
    assert result["n_links"] == 0
    assert result["n_unlinked_tasks"] > 0


# -- CLI ``analyze`` subcommand -------------------------------------------------


@pytest.fixture
def run(config, monkeypatch, capsys):
    """Invoke the CLI against the test's capture home."""
    monkeypatch.setenv("FLOWCEPT_HARNESS_HOME", str(config.home))

    def _run(*argv: str):
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out + captured.err

    return _run


def test_cli_analyze_summary(run, config):
    """`analyze` prints counts, statuses, subagents, and tool usage."""
    record_session(config)
    code, out = run("analyze")
    assert code == cli.OK
    assert "tasks: 4" in out
    assert "ERROR=1" in out
    assert "subagents=1" in out
    assert "Bash=2" in out


def test_cli_analyze_errors(run, config):
    """`analyze --errors` prints failure counts and excerpts."""
    record_session(config)
    code, out = run("analyze", "--errors")
    assert code == cli.OK
    assert "failed tasks: 1 of 4" in out
    assert "1 error found" in out


def test_cli_analyze_slowest(run, config):
    """`analyze --slowest N` prints exactly N rows."""
    record_session(config)
    code, out = run("analyze", "--slowest", "2")
    assert code == cli.OK
    lines = [line for line in out.splitlines() if line.strip().endswith(("depth=0", "depth=1", "depth=2"))]
    assert len(lines) == 2


def test_cli_analyze_links(run, config):
    """`analyze --links` prints the link count."""
    record_session(config)
    code, out = run("analyze", "--links")
    assert code == cli.OK
    assert "cross-framework links: 0" in out


def test_cli_analyze_reports_a_miss(run, config):
    """An unknown session prefix fails with a clear message."""
    record_session(config)
    code, out = run("analyze", "definitely-not-a-session")
    assert code == cli.FAILED
    assert "No session matching" in out


# -- CLI ``analyze --compare`` ----------------------------------------------------

SECOND_SESSION = "sess-def"


def record_second_session(config):
    """Capture a smaller error-free session under a second session id."""
    sid = SECOND_SESSION
    fire(config, "SessionStart", source="startup", model="claude-opus-5", session_id=sid)
    fire(config, "UserPromptSubmit", prompt="run it again", prompt_id="p1", session_id=sid)
    fire(config, "PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "pytest -q"}, session_id=sid)
    fire(config, "PostToolUse", tool_name="Bash", tool_use_id="t1", tool_response={"exit_code": 0}, session_id=sid)
    fire(config, "Stop", last_assistant_message="All green.", session_id=sid)
    fire(config, "SessionEnd", reason="clear", session_id=sid)


def test_cli_analyze_compare(run, config):
    """`analyze --compare A B` prints per-activity count, duration, and error deltas."""
    record_session(config)
    record_second_session(config)
    session_a = ids.workflow_id_for("claude_code", SESSION)
    session_b = ids.workflow_id_for("claude_code", SECOND_SESSION)

    code, out = run("analyze", "--compare", session_a[:8], session_b[:8])
    assert code == cli.OK
    assert f"comparing: A={session_a}  B={session_b}" in out
    assert "tasks: 4 -> 2 (-2)" in out
    assert "count 2 -> 1 (-1)" in out  # Bash ran twice in A, once in B
    assert "errors 50% -> 0%" in out
    assert "only in A: Grep" in out


def test_cli_analyze_compare_reports_a_miss(run, config):
    """An unknown session in either slot fails with a clear message."""
    record_session(config)
    session_a = ids.workflow_id_for("claude_code", SESSION)
    code, out = run("analyze", "--compare", session_a[:8], "definitely-not-a-session")
    assert code == cli.FAILED
    assert "No session matching" in out


def test_cli_analyze_compare_is_exclusive(run, config):
    """--compare rejects a positional session and the single-session flags."""
    record_session(config)
    record_second_session(config)
    session_a = ids.workflow_id_for("claude_code", SESSION)
    session_b = ids.workflow_id_for("claude_code", SECOND_SESSION)

    # argparse itself rejects a positional session next to --compare.
    with pytest.raises(SystemExit):
        cli.main(["analyze", session_a[:8], "--compare", session_a[:8], session_b[:8]])

    code, out = run("analyze", "--compare", session_a[:8], session_b[:8], "--errors")
    assert code == cli.FAILED
    assert "--compare cannot be combined" in out
