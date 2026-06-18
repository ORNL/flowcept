"""Thin MCP wrappers for in-memory workflow message object query tools.

One-liner delegates to :mod:`flowcept.agents.data_query_tools.in_memory_workflow_query_tools`.
MCP context lookup (workflow_msg_obj, custom_guidance) happens here.
"""

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.context_manager import mcp_flowcept
from flowcept.agents.data_query_tools import in_memory_workflow_query_tools as _core


def _get_workflow_context():
    ctx = mcp_flowcept.get_context()
    lifespan = ctx.request_context.lifespan_context
    return lifespan.workflow_msg_obj, lifespan.custom_guidance


@mcp_flowcept.tool()
def execute_generated_workflow_query(query_spec) -> ToolResult:
    """Execute an externally generated workflow query spec against workflow_msg_obj.

    The spec is JSON with ``field_paths`` and optional ``missing`` / ``answer_style`` fields.
    Missing values always return ``info not available``.

    Parameters
    ----------
    query_spec : dict or str
        Workflow query spec.

    Returns
    -------
    ToolResult
    """
    workflow_msg_obj, _ = _get_workflow_context()
    return _core.execute_generated_workflow_query(query_spec=query_spec, workflow_msg_obj=workflow_msg_obj)


@mcp_flowcept.tool()
def run_workflow_query(query: str, llm=None) -> ToolResult:
    """Run a free-text query against the active workflow message object.

    Parameters
    ----------
    query : str
        Free-text question about the workflow.
    llm : callable, optional
        LLM callable. Built from settings if None.

    Returns
    -------
    ToolResult
    """
    workflow_msg_obj, custom_guidance = _get_workflow_context()
    return _core.run_workflow_query(
        query=query,
        workflow_msg_obj=workflow_msg_obj,
        custom_user_guidance=custom_guidance,
        llm=llm,
    )
