"""MCP prompt registrations — all ``@mcp_flowcept.prompt()`` decorators live here.

Separated from the prompt builders in ``prompts/`` so those files have no MCP imports.
"""

from flowcept.agents.mcp.context_manager import ctx_manager, mcp_flowcept, get_df_context, EMPTY_DF_MESSAGE
from flowcept.agents.prompts.in_memory_task_query_prompts import build_pandas_code_prompt
from flowcept.agents.prompts.in_memory_workflow_query_prompts import (
    EMPTY_WORKFLOW_MESSAGE,
    build_workflow_query_prompt as build_workflow_query_prompt_text,
)


@mcp_flowcept.prompt(
    name="build_df_query_prompt",
    title="Build DataFrame Query Prompt",
    description="Build prompt context for external LLM code generation over agent DataFrame context.",
)
def build_df_query_prompt(query: str, context_kind: str = "tasks") -> str:
    """Build the internal pandas-code generation prompt for external LLM orchestration.

    Parameters
    ----------
    query : str
        Natural language question to translate into pandas code.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    str
        Prompt text to guide external LLM code generation.
        Returns an explanatory message when there is no active DataFrame context.
    """
    df, schema, value_examples, custom_user_guidance = get_df_context(context_kind=context_kind)
    if df is None or not len(df):
        return EMPTY_DF_MESSAGE
    current_fields = list(df.columns)
    return build_pandas_code_prompt(
        query,
        schema,
        value_examples,
        custom_user_guidance,
        current_fields,
        context_kind=context_kind,
    )


@mcp_flowcept.prompt(
    name="build_workflow_query_prompt",
    title="Build Workflow Query Prompt",
    description="Build prompt context for external LLM workflow-message field selection.",
)
def build_workflow_query_prompt(query: str) -> str:
    """Build prompt context for external LLM workflow-message field selection.

    Parameters
    ----------
    query : str
        Natural language question about the workflow.

    Returns
    -------
    str
        Prompt text, or empty-workflow message when no workflow is active.
    """
    workflow_msg_obj = ctx_manager.context.workflow_msg_obj
    if not workflow_msg_obj:
        return EMPTY_WORKFLOW_MESSAGE
    return build_workflow_query_prompt_text(query, workflow_msg_obj, ctx_manager.context.custom_guidance)
