"""
Agentic provenance analysis over captured PROV-AGENT records.

``flowcept.agents.prov_analysis`` turns captured provenance into answers:
what happened, what failed, where the time went, how agents behaved, how
work links across frameworks, and how two runs compare. The same pure
functions back four surfaces — the harness MCP server (``analyze_session``,
``analyze_errors``, ``find_slowest``, ``cross_links``), the Flowcept agent
MCP server (``df_*`` / ``db_*`` analysis tools and ``compare_executions``),
the web chat, and ``flowcept-harness analyze``.

This example synthesizes two short coding sessions by replaying Claude Code
hook payloads (one ``handle()`` call per event, exactly as the hooks deliver
them), plants one framework-plugin record that links back to a harness tool
task, then runs every ``prov_analysis.core`` function over the captured
records and prints the results. It runs fully offline: no Claude Code, no
API key, no database. Records also land as PROV-AGENT provenance in JSONL
buffers under ``~/.flowcept/harness/buffers/``.

Run
---
    python examples/agents/prov_analysis/prov_analysis_example.py

Then inspect the same captures from the CLI:

    flowcept-harness sessions
    flowcept-harness analyze            # summary of the most recent session
    flowcept-harness analyze --errors   # failure clustering
    flowcept-harness analyze --slowest 5
    flowcept-harness analyze --links

Plugin configuration
--------------------
The harness plugins are configured with environment variables, not
settings.yaml (see src/flowcept/agents/harness/README.md for the full table):

    FLOWCEPT_HARNESS_ENABLED=1        # master switch (default)
    FLOWCEPT_HARNESS_ONLINE=0         # 1 publishes to a live Flowcept backend
    FLOWCEPT_HARNESS_REDACT=1         # redact credential-shaped values
"""

from __future__ import annotations

import json
import uuid

from flowcept.agents.claude_code.claude_code_plugin import handle
from flowcept.agents.harness.config import load_config
from flowcept.agents.prov_analysis.core import (
    analyze_agent_behavior,
    analyze_errors,
    compare_executions,
    cross_framework_links,
    find_slowest_tasks,
    load_records,
    summarize_execution,
)


def record_session(config, session_id: str, flaky: bool) -> list[dict]:
    """Replay one short Claude Code session and return its captured records.

    The ``flaky`` variant fails its second tool call, so the two sessions
    differ in error rate — which ``compare_executions`` then surfaces.
    """
    records: list[dict] = []

    def fire(event: str, **fields):
        payload = {"hook_event_name": event, "session_id": session_id, "cwd": "/tmp/proj", **fields}
        records.extend(handle(payload, config))

    fire("SessionStart", source="startup", model="claude-opus-5")
    fire("UserPromptSubmit", prompt="fix the flaky network test", prompt_id="p1")
    fire("PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "pytest -q"})
    fire("PostToolUse", tool_name="Bash", tool_use_id="t1", tool_response={"exit_code": 0})
    fire("PreToolUse", tool_name="Bash", tool_use_id="t2", tool_input={"command": "ruff check"})
    if flaky:
        fire("PostToolUseFailure", tool_name="Bash", tool_use_id="t2", error="1 error found")
    else:
        fire("PostToolUse", tool_name="Bash", tool_use_id="t2", tool_response={"exit_code": 0})
    fire("SubagentStart", agent_id="a1", agent_type="Explore")
    fire("PreToolUse", tool_name="Grep", tool_use_id="t3", tool_input={"pattern": "flaky"}, agent_id="a1")
    fire("PostToolUse", tool_name="Grep", tool_use_id="t3", tool_response={"matches": 2}, agent_id="a1")
    fire("SubagentStop", agent_id="a1", agent_type="Explore")
    fire("Stop", last_assistant_message="Fixed the race.")
    fire("SessionEnd", reason="clear")
    return records


def plant_cross_framework_record(records: list[dict]) -> None:
    """Append a framework-plugin record linking back to a harness tool task.

    This mimics what the LangGraph plugin writes when a graph run is started
    by another framework's agent: the parent task id travels in
    ``custom_metadata.source_agent_id``, giving ``cross_framework_links`` an
    explicit edge to walk.
    """
    tool_task = next(r for r in records if r.get("subtype") == "agent_tool")
    records.append(
        {
            "task_id": "lg-1",
            "workflow_id": "wf-langgraph",
            "activity_id": "graph",
            "subtype": "langgraph_graph",
            "status": "FINISHED",
            "custom_metadata": {"source_agent_id": tool_task["task_id"]},
        }
    )


def show(title: str, payload) -> None:
    """Print one analysis result as indented JSON under a heading."""
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2, default=str))


def main():
    """Capture two synthetic sessions and run every analysis over them."""
    config = load_config()
    run_id = uuid.uuid4().hex[:8]

    # Capture two sessions: one clean, one with a failing tool call.
    records_clean = record_session(config, f"prov-analysis-example-a-{run_id}", flaky=False)
    records_flaky = record_session(config, f"prov-analysis-example-b-{run_id}", flaky=True)
    plant_cross_framework_record(records_flaky)

    # load_records also accepts a JSONL buffer path (jsonl_path=...) or a
    # workflow/campaign id to pull from the Flowcept DB; here the records
    # captured above are passed straight through.
    records = load_records(records=records_flaky)

    show("summarize_execution", summarize_execution(records))
    show("analyze_errors", analyze_errors(records))
    show("analyze_agent_behavior", analyze_agent_behavior(records))
    show("find_slowest_tasks (top 3)", find_slowest_tasks(records, limit=3))
    show("cross_framework_links", cross_framework_links(records))
    show("compare_executions (clean vs flaky)", compare_executions(records_clean, records_flaky))

    print("\n[example] Captured two sessions. Inspect them from the CLI with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness analyze")
    print("  flowcept-harness analyze --errors")


if __name__ == "__main__":
    main()
