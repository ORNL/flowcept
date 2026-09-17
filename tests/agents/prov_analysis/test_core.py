"""Unit tests for the provenance analysis core.

Synthetic records cover both shapes the core must understand: the
harness-buffer shape (``agents/harness/prov.py``: ``type`` on every record,
``custom_metadata.llm_usage``) and the framework-plugin shape (LangGraph-style
task dicts without a ``type`` key, token counts in ``generated``).  No MQ,
MongoDB, network, or LLM access is needed.
"""

from __future__ import annotations

import json

import pytest

from flowcept.agents.prov_analysis import core


# -- synthetic records ---------------------------------------------------------


def harness_records() -> list[dict]:
    """One harness session with a subagent, mirroring recorder.py output."""
    return [
        {
            "type": "workflow",
            "workflow_id": "wf-h",
            "campaign_id": "camp-1",
            "name": "claude_code session",
            "subtype": "agent_session",
            "agent_id": "agent-main",
            "status": "FINISHED",
            "started_at": 1000.0,
            "ended_at": 1060.0,
            "custom_metadata": {"harness": "claude_code"},
        },
        {
            "type": "workflow",
            "workflow_id": "wf-sub",
            "parent_workflow_id": "wf-h",
            "name": "subagent:Explore",
            "subtype": "subagent_session",
            "status": "FINISHED",
            "started_at": 1020.0,
            "ended_at": 1030.0,
        },
        {"type": "agent", "agent_id": "agent-main", "name": "claude"},
        {
            "type": "task",
            "task_id": "turn-1",
            "workflow_id": "wf-h",
            "campaign_id": "camp-1",
            "activity_id": "agent_turn",
            "subtype": "ai_model_invocation",
            "agent_id": "agent-main",
            "status": "FINISHED",
            "started_at": 1001.0,
            "ended_at": 1050.0,
            "used": {"prompt": "fix the flake"},
            "generated": {"response": "done"},
            "custom_metadata": {
                "granularity": "turn",
                "harness": "claude_code",
                "llm_usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
            },
        },
        {
            "type": "task",
            "task_id": "tool-1",
            "workflow_id": "wf-h",
            "activity_id": "Bash",
            "subtype": "agent_tool",
            "agent_id": "agent-main",
            "parent_task_id": "turn-1",
            "status": "FINISHED",
            "started_at": 1002.0,
            "ended_at": 1010.0,
            "used": {"command": "pytest -q"},
            "custom_metadata": {"harness": "claude_code", "tool_name": "Bash"},
        },
        {
            "type": "task",
            "task_id": "tool-2",
            "workflow_id": "wf-h",
            "activity_id": "Bash",
            "subtype": "agent_tool",
            "agent_id": "agent-main",
            "parent_task_id": "turn-1",
            "status": "ERROR",
            "started_at": 1011.0,
            "ended_at": 1012.0,
            "stderr": "1 error found",
            "custom_metadata": {"harness": "claude_code", "tool_name": "Bash"},
        },
        {
            "type": "task",
            "task_id": "tool-3",
            "workflow_id": "wf-sub",
            "activity_id": "Grep",
            "subtype": "agent_tool",
            "agent_id": "agent-sub",
            "parent_task_id": "tool-1",
            "status": "FINISHED",
            "started_at": 1021.0,
            "ended_at": 1023.0,
        },
        {
            "type": "task",
            "task_id": "llm-1",
            "workflow_id": "wf-h",
            "activity_id": "llm_interaction",
            "subtype": "ai_model_invocation",
            "agent_id": "agent-main",
            "parent_task_id": "turn-1",
            "status": "FINISHED",
            "started_at": 1030.0,
            "ended_at": 1031.0,
            "custom_metadata": {"granularity": "call", "llm_usage": {"total_tokens": 25}},
        },
    ]


def framework_records() -> list[dict]:
    """LangGraph-plugin-shaped task dicts (no ``type`` key) with a cross link."""
    return [
        {
            "task_id": "lg-graph-1",
            "workflow_id": "wf-lg",
            "activity_id": "LangGraph",
            "subtype": "langgraph_graph",
            "status": "FINISHED",
            "started_at": 2000.0,
            "ended_at": 2005.0,
            "used": {"inputs": {"value": 1, "_source_agent_id": "tool-1"}},
            "custom_metadata": {"graph_name": "LangGraph", "source_agent_id": "tool-1"},
        },
        {
            "task_id": "lg-node-1",
            "workflow_id": "wf-lg",
            "activity_id": "add_one",
            "subtype": "langgraph_node",
            "parent_task_id": "lg-graph-1",
            "status": "FINISHED",
            "started_at": 2001.0,
            "ended_at": 2003.0,
            "custom_metadata": {"node_name": "add_one", "source_agent_id": "tool-1"},
        },
        {
            "task_id": "lg-llm-1",
            "workflow_id": "wf-lg",
            "activity_id": "gpt-test",
            "subtype": "llm_call",
            "parent_task_id": "lg-node-1",
            "status": "FINISHED",
            "started_at": 2001.5,
            "ended_at": 2002.5,
            "generated": {"text": "hi", "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        {
            "task_id": "lg-tool-1",
            "workflow_id": "wf-lg",
            "activity_id": "search",
            "subtype": "tool_call",
            "parent_task_id": "lg-node-1",
            "status": "ERROR",
            "started_at": 2003.0,
            "ended_at": 2004.0,
            "stderr": "boom",
        },
    ]


# -- load_records --------------------------------------------------------------


def test_load_records_from_jsonl(tmp_path):
    """load_records reads dict lines from JSONL and skips garbage lines."""
    path = tmp_path / "buffer.jsonl"
    lines = [json.dumps(r) for r in harness_records()] + ["", "not json", '["not", "a", "dict"]']
    path.write_text("\n".join(lines), encoding="utf-8")
    records = core.load_records(jsonl_path=str(path))
    assert len(records) == len(harness_records())
    assert records[0]["workflow_id"] == "wf-h"


def test_load_records_passes_records_through():
    """load_records returns a copy of an explicitly passed record list."""
    given = harness_records()
    out = core.load_records(records=given)
    assert out == given
    assert out is not given, "must return a copy, not the caller's list"


def test_load_records_with_no_source_is_empty():
    """load_records with no source returns an empty list."""
    assert core.load_records() == []


# -- summarize_execution -------------------------------------------------------


def test_summarize_execution_counts_and_bounds():
    """Summary reports counts, statuses, bounds, campaigns, and agents."""
    summary = core.summarize_execution(harness_records())
    assert summary["n_workflows"] == 2
    assert summary["n_tasks"] == 5
    assert summary["tasks_by_subtype"] == {"ai_model_invocation": 2, "agent_tool": 3}
    assert summary["tasks_by_activity"]["Bash"] == 2
    assert summary["status_counts"] == {"FINISHED": 4, "ERROR": 1}
    assert summary["started_at"] == 1001.0
    assert summary["ended_at"] == 1050.0
    assert summary["total_elapsed_seconds"] == pytest.approx(49.0)
    assert summary["campaigns"] == ["camp-1"]
    assert "agent-main" in summary["agents"]
    assert summary["agent_names"] == ["claude"]


def test_summarize_execution_token_usage_from_both_shapes():
    """Token totals combine harness llm_usage and plugin generated fields."""
    summary = core.summarize_execution(harness_records() + framework_records())
    totals = summary["token_usage"]["totals"]
    # 100+10 prompt, 50+5 completion, 150+25+15 total
    assert totals["prompt_tokens"] == 110
    assert totals["completion_tokens"] == 55
    assert totals["total_tokens"] == 190
    assert summary["token_usage"]["n_tasks_with_usage"] == 3


def test_summarize_execution_filters_by_workflow_id():
    """workflow_id restricts the summary to one workflow's records."""
    summary = core.summarize_execution(harness_records(), workflow_id="wf-sub")
    assert summary["n_tasks"] == 1
    assert summary["tasks_by_activity"] == {"Grep": 1}
    assert summary["n_workflows"] == 1


def test_summarize_execution_handles_framework_tasks_without_type():
    """Plugin task dicts without a type key still count as tasks."""
    summary = core.summarize_execution(framework_records())
    assert summary["n_tasks"] == 4
    assert summary["n_workflows"] == 0
    assert summary["tasks_by_subtype"]["langgraph_node"] == 1


def test_summarize_execution_empty_input():
    """An empty record list yields a zeroed summary."""
    summary = core.summarize_execution([])
    assert summary["n_records"] == 0
    assert summary["n_tasks"] == 0
    assert summary["total_elapsed_seconds"] is None
    assert summary["token_usage"]["totals"] == {}
    assert summary["activities"] == []


# -- analyze_errors ------------------------------------------------------------


def test_analyze_errors_groups_by_activity_with_excerpts():
    """Failures group by activity with rates and stderr excerpts."""
    errors = core.analyze_errors(harness_records())
    assert errors["n_failed"] == 1
    assert errors["overall_error_rate"] == pytest.approx(0.2)
    entry = errors["by_activity"]["Bash"]
    assert entry["n_failed"] == 1
    assert entry["n_total"] == 2
    assert entry["error_rate"] == pytest.approx(0.5)
    assert entry["excerpts"] == ["1 error found"]


def test_analyze_errors_failure_time_bounds():
    """First/last failure times span both record shapes."""
    errors = core.analyze_errors(harness_records() + framework_records())
    assert errors["n_failed"] == 2
    assert errors["first_failure_at"] == 1011.0
    assert errors["last_failure_at"] == 2003.0
    assert errors["first_failure_at_utc"] is not None


def test_analyze_errors_without_failures():
    """No failed tasks yields empty groupings and a zero rate."""
    ok_only = [r for r in harness_records() if r.get("status") != "ERROR"]
    errors = core.analyze_errors(ok_only)
    assert errors["n_failed"] == 0
    assert errors["by_activity"] == {}
    assert errors["first_failure_at"] is None
    assert errors["overall_error_rate"] == 0.0


def test_analyze_errors_empty_input():
    """An empty record list yields no error rate."""
    errors = core.analyze_errors([])
    assert errors["n_tasks"] == 0
    assert errors["overall_error_rate"] is None


# -- analyze_agent_behavior ------------------------------------------------------


def test_agent_behavior_per_agent_counts():
    """Per-agent turns, tool calls, LLM calls, tokens, and durations."""
    behavior = core.analyze_agent_behavior(harness_records())
    main = behavior["agents"]["agent-main"]
    assert main["turns"] == 1
    assert main["llm_calls"] == 1  # granularity=call record
    assert main["tool_calls"] == 2
    assert main["tool_calls_by_tool"] == {"Bash": 2}
    assert main["n_errors"] == 1
    assert main["token_usage"]["total_tokens"] == 175
    assert main["max_task_seconds"] == pytest.approx(49.0)
    sub = behavior["agents"]["agent-sub"]
    assert sub["tool_calls_by_tool"] == {"Grep": 1}


def test_agent_behavior_sessions_and_subagents():
    """Session workflows and subagent counts are reported."""
    behavior = core.analyze_agent_behavior(harness_records())
    assert behavior["n_subagent_sessions"] == 1
    assert len(behavior["sessions"]) == 1
    session = behavior["sessions"][0]
    assert session["workflow_id"] == "wf-h"
    assert session["n_subagents"] == 1
    assert session["elapsed_seconds"] == pytest.approx(60.0)


def test_agent_behavior_framework_shape_falls_back_to_workflow_key():
    """Plugin records without agent_id key by workflow_id."""
    behavior = core.analyze_agent_behavior(framework_records())
    entry = behavior["agents"]["wf-lg"]
    assert entry["llm_calls"] == 1
    assert entry["tool_calls_by_tool"] == {"search": 1}
    assert entry["token_usage"]["total_tokens"] == 15


def test_agent_behavior_empty_input():
    """An empty record list yields an empty behavior profile."""
    behavior = core.analyze_agent_behavior([])
    assert behavior == {"agents": {}, "sessions": [], "n_subagent_sessions": 0}


# -- find_slowest_tasks ----------------------------------------------------------


def test_find_slowest_orders_and_limits():
    """Slowest tasks come back longest first, capped by limit."""
    rows = core.find_slowest_tasks(harness_records(), limit=3)
    assert [r["task_id"] for r in rows] == ["turn-1", "tool-1", "tool-3"]
    assert rows[0]["elapsed_seconds"] == pytest.approx(49.0)
    assert rows[0]["status"] == "FINISHED"


def test_find_slowest_reports_parent_depth():
    """Parent-chain depth follows parent_task_id links."""
    rows = core.find_slowest_tasks(harness_records(), limit=10)
    by_id = {r["task_id"]: r for r in rows}
    assert by_id["turn-1"]["parent_depth"] == 0
    assert by_id["tool-1"]["parent_depth"] == 1
    assert by_id["tool-3"]["parent_depth"] == 2


def test_find_slowest_skips_tasks_without_timing():
    """Tasks without timing are excluded; empty input yields []."""
    records = harness_records() + [{"type": "task", "task_id": "no-time", "activity_id": "X"}]
    rows = core.find_slowest_tasks(records, limit=100)
    assert all(r["task_id"] != "no-time" for r in rows)
    assert core.find_slowest_tasks([], limit=5) == []


# -- cross_framework_links --------------------------------------------------------


def test_cross_framework_links_builds_edges():
    """Edges are built from source_agent_id pointers across shapes."""
    result = core.cross_framework_links(harness_records() + framework_records())
    assert result["n_links"] == 2
    targets = {link["target_task_id"]: link for link in result["links"]}
    assert set(targets) == {"lg-graph-1", "lg-node-1"}
    graph_link = targets["lg-graph-1"]
    assert graph_link["source_task_id"] == "tool-1"
    assert graph_link["target_workflow_id"] == "wf-lg"
    # Source is a harness (claude_code) task; target is a langgraph task.
    assert graph_link["frameworks"] == ["claude_code", "langgraph"]


def test_cross_framework_links_from_used_inputs_only():
    """The raw _source_agent_id inside used.inputs also links."""
    records = [
        {
            "task_id": "t1",
            "workflow_id": "w1",
            "subtype": "langgraph_graph",
            "used": {"inputs": {"_source_agent_id": "external-1"}},
        }
    ]
    result = core.cross_framework_links(records)
    assert result["n_links"] == 1
    assert result["links"][0]["source_task_id"] == "external-1"
    assert result["n_unlinked_tasks"] == 0


def test_cross_framework_links_counts_unlinked():
    """Sessions without pointers report zero links and all tasks unlinked."""
    result = core.cross_framework_links(harness_records())
    assert result["n_links"] == 0
    assert result["n_unlinked_tasks"] == 5
    assert core.cross_framework_links([]) == {
        "links": [],
        "n_links": 0,
        "n_unlinked_tasks": 0,
        "frameworks_seen": [],
    }


# -- compare_executions ------------------------------------------------------------


def test_compare_executions_deltas():
    """Per-activity count, duration, and error-rate deltas are computed."""
    records_a = harness_records()
    records_b = [dict(r) for r in harness_records()]
    # Make run B's failing Bash task succeed and take longer.
    for record in records_b:
        if record.get("task_id") == "tool-2":
            record["status"] = "FINISHED"
            record["ended_at"] = 1021.0
    result = core.compare_executions(records_a, records_b)
    bash = result["activities"]["Bash"]
    assert bash["count_a"] == bash["count_b"] == 2
    assert bash["count_delta"] == 0
    assert bash["error_rate_a"] == pytest.approx(0.5)
    assert bash["error_rate_b"] == 0.0
    assert bash["error_rate_delta"] == pytest.approx(-0.5)
    assert bash["elapsed_avg_delta"] == pytest.approx(4.5)
    assert result["totals"]["n_tasks_a"] == 5


def test_compare_executions_disjoint_activities():
    """Activities present in only one run are listed separately."""
    result = core.compare_executions(harness_records(), framework_records())
    assert "Bash" in result["only_in_a"]
    assert "add_one" in result["only_in_b"]
    assert result["activities"]["Bash"]["count_b"] == 0
    assert result["activities"]["Bash"]["elapsed_avg_b"] is None


def test_compare_executions_empty_inputs():
    """Comparing empty runs yields empty activities and null deltas."""
    result = core.compare_executions([], [])
    assert result["activities"] == {}
    assert result["totals"]["n_tasks_a"] == 0
    assert result["totals"]["total_elapsed_delta"] is None
