"""ToolResult wrappers over :mod:`flowcept.agents.prov_analysis.core`.

Framework-free (no MCP, no LangChain imports): each function wraps one core
analysis in the ``ToolResult`` convention used by ``data_query_tools``, so both
the MCP surface and the chat tool registry can reuse them without drift.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from flowcept.agents.prov_analysis import core
from flowcept.agents.tool_result import ToolResult


def _guarded(tool_name: str):
    """Decorate a tool function: convert exceptions to ToolResult error codes."""

    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except ValueError as e:
                return ToolResult(code=400, result=str(e), tool_name=tool_name)
            except Exception as e:
                from flowcept.commons.flowcept_logger import FlowceptLogger

                FlowceptLogger().exception(e)
                return ToolResult(code=499, result=f"Error in {tool_name}: {e}", tool_name=tool_name)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    return decorator


@_guarded("summarize_execution")
def summarize_execution(records: List[Dict[str, Any]], workflow_id: Optional[str] = None) -> ToolResult:
    """Summarize an execution (counts, durations, statuses, agents, token usage)."""
    return ToolResult(
        code=301,
        result=core.summarize_execution(records, workflow_id=workflow_id),
        tool_name="summarize_execution",
    )


@_guarded("analyze_errors")
def analyze_errors(records: List[Dict[str, Any]]) -> ToolResult:
    """Analyze failed tasks: per-activity failure counts, error rates, excerpts."""
    return ToolResult(code=301, result=core.analyze_errors(records), tool_name="analyze_errors")


@_guarded("analyze_agent_behavior")
def analyze_agent_behavior(records: List[Dict[str, Any]]) -> ToolResult:
    """Profile per-agent behavior: turns, tool calls, LLM calls, token usage."""
    return ToolResult(code=301, result=core.analyze_agent_behavior(records), tool_name="analyze_agent_behavior")


@_guarded("find_slowest_tasks")
def find_slowest_tasks(records: List[Dict[str, Any]], limit: int = 10) -> ToolResult:
    """Return the slowest tasks, longest elapsed first."""
    return ToolResult(
        code=301,
        result={"tasks": core.find_slowest_tasks(records, limit=limit)},
        tool_name="find_slowest_tasks",
    )


@_guarded("cross_framework_links")
def cross_framework_links(records: List[Dict[str, Any]]) -> ToolResult:
    """List cross-framework provenance links (source_agent_id edges)."""
    return ToolResult(code=301, result=core.cross_framework_links(records), tool_name="cross_framework_links")


@_guarded("compare_executions")
def compare_executions(records_a: List[Dict[str, Any]], records_b: List[Dict[str, Any]]) -> ToolResult:
    """Compare two executions per activity (count/duration/error-rate deltas)."""
    return ToolResult(code=301, result=core.compare_executions(records_a, records_b), tool_name="compare_executions")
