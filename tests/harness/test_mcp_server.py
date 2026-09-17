"""Tests for the MCP provenance server.

The tools are exercised through the server's own registry rather than by
calling the local functions, so a rename or signature change in the SDK's
decorator is caught here.
"""

from __future__ import annotations

import pytest

from .test_claude_code import fire

pytest.importorskip("mcp")

from flowcept.agents.harness import mcp_server  # noqa: E402


@pytest.fixture
def server(config):
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
    return mcp_server.build_server(config)


def call(server, name: str, **kwargs):
    """Invoke a registered tool by name, as a client would."""
    fn = getattr(server, "_tool_functions", {}).get(name)
    if fn is None:
        # Both SDK generations keep the undecorated callable reachable; fall
        # back to the module-level lookup used by the tool manager.
        manager = getattr(server, "_tool_manager", None)
        tool = manager.get_tool(name) if manager else None
        fn = getattr(tool, "fn", None)
    assert fn is not None, f"tool {name!r} is not registered"
    return fn(**kwargs)


def test_expected_tools_are_registered(server):
    manager = getattr(server, "_tool_manager", None)
    assert manager is not None, "SDK no longer exposes a tool manager"
    names = {t.name for t in manager.list_tools()}
    assert names == {
        "list_sessions",
        "get_session",
        "search_tool_calls",
        "session_stats",
        "record_event",
        "generate_report",
        "analyze_session",
        "analyze_errors",
        "find_slowest",
        "cross_links",
    }


def test_every_tool_has_a_description(server):
    for tool in server._tool_manager.list_tools():
        assert tool.description, f"{tool.name} has no description for the model to read"


def test_list_sessions(server):
    sessions = call(server, "list_sessions")
    assert len(sessions) == 1
    entry = sessions[0]
    assert entry["harness"] == "claude_code"
    assert entry["status"] == "FINISHED"
    assert entry["totals"]["tool_calls"] == 3
    assert entry["totals"]["tool_errors"] == 1


def test_get_session_separates_subagent_work(server):
    result = call(server, "get_session")
    assert result["status"] == "FINISHED"
    assert [s["name"] for s in result["subagents"]] == ["subagent:Explore"]

    grep = next(a for a in result["activity"] if a["name"] == "Grep")
    assert grep["in_subagent"] == "subagent:Explore"
    bash = next(a for a in result["activity"] if a["name"] == "Bash")
    assert "in_subagent" not in bash


def test_get_session_omits_io_by_default(server):
    activity = call(server, "get_session")["activity"]
    assert all("used" not in a for a in activity)
    with_io = call(server, "get_session", include_io=True)["activity"]
    assert any(a.get("used") for a in with_io)


def test_get_session_reports_a_miss(server):
    assert "error" in call(server, "get_session", session="nope")


def test_search_by_status_finds_failures(server):
    hits = call(server, "search_tool_calls", status="ERROR")
    assert len(hits) == 1
    assert hits[0]["error"] == "1 error found"


def test_search_by_content(server):
    hits = call(server, "search_tool_calls", contains="ruff")
    assert len(hits) == 1
    assert hits[0]["tool"] == "Bash"


def test_search_respects_the_limit(server):
    assert len(call(server, "search_tool_calls", limit=1)) == 1


def test_session_stats_aggregates_by_tool(server):
    stats = call(server, "session_stats")
    assert stats["by_tool"]["Bash"] == {"calls": 2, "errors": 1, "seconds": pytest.approx(0, abs=1)}
    assert stats["by_tool"]["Grep"]["calls"] == 1


def test_record_event_writes_provenance(config):
    server = mcp_server.build_server(config)
    assert call(server, "record_event", kind="session_start", session_id="m1", harness="my_agent")["recorded"]
    result = call(
        server,
        "record_event",
        kind="tool_post",
        session_id="m1",
        harness="my_agent",
        tool_name="query_db",
        tool_input={"sql": "select 1"},
    )
    assert result["recorded"] == 1

    hits = call(server, "search_tool_calls", tool_name="query_db")
    assert hits[0]["used"]["sql"] == "select 1"


def test_record_event_rejects_an_unknown_kind(config):
    server = mcp_server.build_server(config)
    assert "error" in call(server, "record_event", kind="nonsense", session_id="m1")
