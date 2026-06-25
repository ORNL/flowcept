"""MCP tools for workflow-scoped schema context."""

from typing import Optional

from flowcept.agents.mcp.context_manager import ctx_manager, mcp_flowcept
from flowcept.agents.prompts.db_query_prompts import build_db_schema_context
from flowcept.agents.tool_result import ToolResult
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def get_workflow_schema_context(workflow_id: Optional[str] = None) -> ToolResult:
    """Return workflow-scoped dynamic schema context for DB and runtime queries."""
    snapshot = ctx_manager.schema_manager.get_workflow_schema_snapshot(workflow_id)
    if not snapshot:
        return ToolResult(code=404, result="No workflow schema context is available.")
    prompt_context = build_db_schema_context(
        dynamic_schema=snapshot.get("dynamic_schema"),
        example_values=snapshot.get("value_examples"),
        current_fields=snapshot.get("current_fields"),
    )
    return ToolResult(
        code=301,
        result={"workflow_id": workflow_id, "schema": snapshot, "prompt_context": prompt_context},
        tool_name="get_workflow_schema_context",
    )
