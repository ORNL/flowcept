"""MCP prompt registrations — all ``@mcp_flowcept.prompt()`` decorators live here.

Separated from the prompt builders in ``prompts/`` so those files have no MCP imports.
"""

from flowcept.agents.mcp.context_manager import mcp_flowcept, get_df_context, EMPTY_DF_MESSAGE
from flowcept.agents.prompts.df_query_prompts import build_pandas_code_prompt


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
