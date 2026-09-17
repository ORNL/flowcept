"""Registration and offline behavior of the Flowcept agent analysis MCP tools.

Importing ``analysis_mcp_tools`` must register every tool on ``mcp_flowcept``.
Skips gracefully when the MCP/agent stack cannot be imported in this
environment (heavy config or missing extras); no MQ, MongoDB, network, or LLM
keys are needed otherwise.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mcp")
pytest.importorskip("pandas")

try:
    import flowcept.agents.mcp.mcp_tools.analysis_mcp_tools as analysis_mcp_tools
    from flowcept.agents.mcp.context_manager import ctx_manager, mcp_flowcept
except Exception as exc:  # pragma: no cover - environment-dependent
    pytest.skip(f"agent MCP stack unavailable: {exc}", allow_module_level=True)

EXPECTED_TOOLS = {
    "df_summarize_execution",
    "df_analyze_errors",
    "df_agent_behavior",
    "df_find_slowest",
    "df_cross_framework_links",
    "db_summarize_execution",
    "db_analyze_errors",
    "db_agent_behavior",
    "db_find_slowest",
    "db_cross_framework_links",
    "compare_executions",
}


def test_analysis_tools_are_registered():
    """The four analysis tools are registered on the harness server."""
    names = {t.name for t in mcp_flowcept._tool_manager.list_tools()}
    assert EXPECTED_TOOLS <= names


def test_analysis_tools_have_descriptions():
    """Every analysis tool carries a description for the model."""
    by_name = {t.name: t for t in mcp_flowcept._tool_manager.list_tools()}
    for name in EXPECTED_TOOLS:
        assert by_name[name].description, f"{name} has no description for the model to read"


def test_df_tools_report_empty_context():
    """DF tools return 404 when no records are loaded."""
    ctx_manager.context.reset_context()
    result = analysis_mcp_tools.df_summarize_execution()
    assert result.code == 404


def test_df_tools_analyze_loaded_context_records():
    """DF tools analyze the raw records held in the agent context."""
    ctx_manager.context.reset_context()
    ctx_manager.context.workflow_msg_obj = {
        "type": "workflow",
        "workflow_id": "wf-1",
        "status": "FINISHED",
    }
    ctx_manager.context.tasks = [
        {
            "type": "task",
            "task_id": "t1",
            "workflow_id": "wf-1",
            "activity_id": "train",
            "subtype": "agent_tool",
            "status": "FINISHED",
            "started_at": 1.0,
            "ended_at": 3.0,
        },
        {
            "type": "task",
            "task_id": "t2",
            "workflow_id": "wf-1",
            "activity_id": "train",
            "subtype": "agent_tool",
            "status": "ERROR",
            "stderr": "exploded",
            "started_at": 3.0,
            "ended_at": 4.0,
        },
    ]
    try:
        summary = analysis_mcp_tools.df_summarize_execution()
        assert summary.code == 301
        assert summary.result["n_tasks"] == 2
        assert summary.result["status_counts"]["ERROR"] == 1

        errors = analysis_mcp_tools.df_analyze_errors()
        assert errors.code == 301
        assert errors.result["by_activity"]["train"]["excerpts"] == ["exploded"]

        slowest = analysis_mcp_tools.df_find_slowest(limit=1)
        assert slowest.code == 301
        assert slowest.result["tasks"][0]["task_id"] == "t1"

        links = analysis_mcp_tools.df_cross_framework_links()
        assert links.code == 301
        assert links.result["n_links"] == 0

        behavior = analysis_mcp_tools.df_agent_behavior()
        assert behavior.code == 301
        assert behavior.result["agents"]["wf-1"]["tool_calls"] == 2
    finally:
        ctx_manager.context.reset_context()
