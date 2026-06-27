"""MCP tool for schema context — unified for both DB and DF query paths."""

from typing import Optional

from flowcept.agents.mcp.context_manager import ctx_manager, mcp_flowcept, get_df_context, EMPTY_DF_MESSAGE
from flowcept.agents.prompts.db_query_prompts import build_db_schema_context
from flowcept.agents.tool_result import ToolResult
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task


@mcp_flowcept.tool()
@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)
def get_schema_context(tool_context: str = "db", workflow_id: Optional[str] = None) -> ToolResult:
    """Return schema context for the active query path.

    For the DB path (``tool_context="db"``) returns a workflow-scoped dynamic
    schema (field names and example values) suitable for writing Mongo filters.
    For the DF path (``tool_context="df"``) returns the in-memory DataFrame
    schema (ALLOWED_FIELDS, per-activity inputs/outputs, example values)
    suitable for writing pandas code.

    Parameters
    ----------
    tool_context : str, optional
        ``"db"`` (default) or ``"df"``.
    workflow_id : str, optional
        Required for the DB path to scope the schema to a specific workflow.

    Returns
    -------
    ToolResult
        ``result`` holds ``{"tool_context": ..., "prompt_context": ...}``.
    """
    if tool_context == "df":
        from flowcept.agents.prompts.df_query_prompts import build_pandas_code_prompt

        df, schema, value_examples, custom_guidance = get_df_context(context_kind="tasks")
        if df is None or not len(df):
            return ToolResult(code=404, result=EMPTY_DF_MESSAGE, tool_name="get_schema_context")
        prompt_context = build_pandas_code_prompt(
            "",
            schema,
            value_examples,
            custom_guidance,
            list(df.columns),
            context_kind="tasks",
        )
    else:
        snapshot = ctx_manager.schema_manager.get_workflow_schema_snapshot(workflow_id)
        if not snapshot:
            return ToolResult(
                code=404, result="No workflow schema context is available.", tool_name="get_schema_context"
            )
        prompt_context = build_db_schema_context(
            dynamic_schema=snapshot.get("dynamic_schema"),
            example_values=snapshot.get("value_examples"),
            current_fields=snapshot.get("current_fields"),
        )

    return ToolResult(
        code=301,
        result={"tool_context": tool_context, "prompt_context": prompt_context},
        tool_name="get_schema_context",
    )
