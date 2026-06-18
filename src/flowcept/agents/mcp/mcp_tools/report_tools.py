"""MCP tool for generating workflow provenance cards.

Split from ``general_tools.py`` — thin wrapper around ``Flowcept.generate_report``.
"""

from flowcept import Flowcept
from flowcept.agents.tool_result import ToolResult
from flowcept.agents.context_manager import mcp_flowcept


@mcp_flowcept.tool()
def generate_workflow_card(
    workflow_id: str = None,
    campaign_id: str = None,
    input_jsonl_path: str = None,
) -> ToolResult:
    """Generate and return a markdown workflow card as text.

    Exactly one of ``workflow_id``, ``campaign_id``, or ``input_jsonl_path`` must be provided.

    Parameters
    ----------
    workflow_id : str, optional
        Query by workflow identifier.
    campaign_id : str, optional
        Query by campaign identifier (produces a campaign-level card).
    input_jsonl_path : str, optional
        Path to a Flowcept JSONL buffer file used as input instead of the DB.

    Returns
    -------
    ToolResult
        ``code=301`` with markdown text in ``result["markdown"]`` on success,
        or an error payload on failure.
    """
    try:
        if not any([workflow_id, campaign_id, input_jsonl_path]):
            return ToolResult(code=400, result="One of workflow_id, campaign_id, or input_jsonl_path is required.")

        stats = Flowcept.generate_report(
            report_type="workflow_card",
            format="markdown",
            workflow_id=workflow_id,
            campaign_id=campaign_id,
            input_jsonl_path=input_jsonl_path,
        )
        return ToolResult(
            code=301,
            result={
                "workflow_id": workflow_id,
                "campaign_id": campaign_id,
                "markdown": stats["markdown"],
            },
        )
    except Exception as e:
        return ToolResult(code=499, result=str(e))
