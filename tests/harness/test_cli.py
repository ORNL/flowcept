"""Tests for the ``flowcept-harness`` command."""

from __future__ import annotations

import json

import pytest

from flowcept.agents.harness import cli

from .test_claude_code import fire


@pytest.fixture
def run(config, monkeypatch, capsys):
    """Invoke the CLI against the test's capture home."""
    monkeypatch.setenv("FLOWCEPT_HARNESS_HOME", str(config.home))

    def _run(*argv: str):
        code = cli.main(list(argv))
        return code, capsys.readouterr().out

    return _run


@pytest.fixture
def recorded(config):
    fire(config, "SessionStart", source="startup", model="claude-opus-5")
    fire(config, "UserPromptSubmit", prompt="fix it", prompt_id="p1")
    fire(config, "PreToolUse", tool_name="Edit", tool_use_id="t1", tool_input={"file_path": "a.py"})
    fire(config, "PostToolUse", tool_name="Edit", tool_use_id="t1", tool_response={"ok": True})
    fire(config, "SessionEnd", reason="clear")
    return config


def test_status_reports_the_capture_home(run, config):
    code, out = run("status")
    assert code == cli.OK
    assert str(config.home) in out


def test_sessions_lists_nothing_before_capture(run):
    code, out = run("sessions")
    assert code == cli.OK
    assert "No sessions" in out


def test_sessions_lists_a_captured_session(run, recorded):
    code, out = run("sessions")
    assert code == cli.OK
    assert "FINISHED" in out
    assert "claude_code session" in out
    assert "tool_calls=1" in out


def test_show_lists_activity(run, recorded):
    code, out = run("show")
    assert code == cli.OK
    assert "Edit" in out
    assert "agent_turn" in out


def test_show_says_so_when_there_is_no_activity(run, config):
    fire(config, "SessionStart", source="startup")
    code, out = run("show")
    assert code == cli.OK
    assert "no activity" in out


def test_hook_subcommand_records(run, config, buffer_records, monkeypatch):
    payload = {"session_id": "cli-1", "cwd": "/w", "source": "startup", "model": "m"}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))

    code, _ = run("hook", "--event", "SessionStart")
    assert code == cli.OK
    assert any(r.get("type") == "workflow" for r in buffer_records())


def test_hook_subcommand_routes_to_the_generic_adapter(run, buffer_records, monkeypatch):
    payload = {"event": "session-start", "session_id": "cx-1", "cwd": "/repo"}
    monkeypatch.setattr("sys.stdin", _Stdin(json.dumps(payload)))

    code, _ = run("hook", "--harness", "codex")
    assert code == cli.OK
    workflow = next(r for r in buffer_records() if r.get("type") == "workflow")
    assert workflow["custom_metadata"]["harness"] == "codex"


def test_hook_never_fails_on_garbage(run, monkeypatch):
    """A hook that exits non-zero is surfaced to the user mid-session."""
    monkeypatch.setattr("sys.stdin", _Stdin("this is not json"))
    code, _ = run("hook", "--event", "SessionStart")
    assert code == cli.OK


def test_repair_closes_a_dangling_session(run, config, buffer_records):
    fire(config, "SessionStart", source="startup")
    fire(config, "UserPromptSubmit", prompt="hi", prompt_id="p1")

    code, out = run("repair")
    assert code == cli.OK
    assert "1 session(s) repaired" in out

    workflow = next(r for r in buffer_records() if r.get("type") == "workflow")
    assert workflow["status"] == "FINISHED"
    assert workflow["custom_metadata"]["end_reason"] == "repaired"


def test_repair_is_idempotent(run, recorded):
    code, out = run("repair")
    assert code == cli.OK
    assert "0 session(s) repaired" in out


def test_flush_dry_run_needs_no_backend(run, recorded, monkeypatch):
    pytest.importorskip("flowcept")
    published = []

    class FakeMQ:
        def bulk_publish(self, records):
            published.extend(records)

        def stop(self):
            pass

    monkeypatch.setattr("flowcept.commons.daos.mq_dao.mq_dao_base.MQDao.build", staticmethod(FakeMQ))
    code, out = run("flush", "--dry-run")
    assert code == cli.OK
    assert "would publish" in out
    assert published == [], "a dry run must not publish"


def test_flush_publishes_and_can_remove(run, recorded, config, monkeypatch):
    pytest.importorskip("flowcept")
    published = []

    class FakeMQ:
        def bulk_publish(self, records):
            published.extend(records)

        def stop(self):
            pass

    monkeypatch.setattr("flowcept.commons.daos.mq_dao.mq_dao_base.MQDao.build", staticmethod(FakeMQ))
    code, out = run("flush", "--all", "--remove")
    assert code == cli.OK
    assert published, "records should reach the backend"
    assert list(config.buffers_dir.glob("*.jsonl")) == []


def test_install_prints_wiring(run):
    code, out = run("install")
    assert code == cli.OK
    assert "PreToolUse" in out


class _Stdin:
    """Minimal stdin stand-in; the adapter only ever calls read()."""

    def __init__(self, data: str):
        self._data = data

    def read(self) -> str:
        return self._data
