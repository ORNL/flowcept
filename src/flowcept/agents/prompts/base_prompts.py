# flake8: noqa: E501
"""Base prompt builders using SCHEMA_CONTEXT for schema-aware task analysis.

These replace the hardcoded schema strings in ``general_prompts.py`` with
live schema tables derived from ``SCHEMA_CONTEXT`` (populated at MCP server startup).
"""

from flowcept.agents.schema_introspection import SCHEMA_CONTEXT

BASE_ROLE = (
    "You are a helpful assistant analyzing provenance data from a large-scale workflow composed of multiple tasks."
)

SMALL_TALK_PROMPT = "Act as a Workflow Provenance Specialist. I would like to interact with you, but please be concise and brief. This is my message:\n"

ROUTING_PROMPT = (
    "You are an orchestrator that routes user messages to the right tool. "
    "You MUST respond with one of these exact words only, nothing else:\n"
    "- 'small_talk': casual conversation, greetings, or questions unrelated to workflow data\n"
    "- 'in_context_query': questions about the current loaded task data or workflow data in memory\n"
    "- 'plot': requests to generate a chart, graph, or visualization\n"
    "- 'in_chat_query': provenance queries that need database access (historical data, specific workflow IDs, etc.)\n"
    "User message: "
)


def _build_schema_table() -> str:
    """Build a markdown schema reference table from SCHEMA_CONTEXT."""
    rows = [
        "| Field | Type | Description |",
        "|---|---|---|",
    ]
    for field in SCHEMA_CONTEXT.get("task_fields", []):
        rows.append(f"| `{field['name']}` | {field['type']} | {field['description']} |")
    for field in SCHEMA_CONTEXT.get("telemetry_summary_fields", []):
        rows.append(f"| `telemetry_summary.{field['name']}` | {field['type']} | {field['description']} |")
    if not SCHEMA_CONTEXT:
        rows.append("| *(schema not yet loaded)* | | |")
    return "\n".join(rows)


def _build_data_schema_prompt() -> str:
    """Return a schema description string for a task object."""
    return (
        "A task object has its provenance: input data is stored in the 'used' field (column prefix `used.`), "
        "output in the 'generated' field (column prefix `generated.`). "
        "Tasks sharing the same 'workflow_id' belong to the same workflow execution trace. "
        "Pay attention to the 'tags' field, as it may indicate critical tasks. "
        "The 'telemetry_summary' field reports CPU, disk, memory, and network usage, along with 'duration_sec'. "
        "Task placement is stored in the 'hostname' field.\n\n"
        "### Known task fields\n\n" + _build_schema_table()
    )


def build_single_task_prompt(task_obj: dict) -> str:
    """Build a prompt for single-task analysis using the live schema context.

    Parameters
    ----------
    task_obj : dict
        The task object to analyze.

    Returns
    -------
    str
        Formatted analysis prompt.
    """
    return (
        f"{BASE_ROLE} You are focusing now on a particular task object.\n\n"
        f"{_build_data_schema_prompt()}\n\n"
        "Your job is to analyze this single task. Find any anomalies, relationships, or correlations between input, "
        "output, resource usage metrics, task duration, and task placement. "
        "Correlations involving 'used' vs 'generated' data are especially important. "
        "So are relationships between (used or generated) data and resource metrics. "
        "Highlight outliers or critical information and give actionable insights or recommendations. "
        "Explain what this task may be doing, using the data provided.\n\n"
        f"Task object:\n```json\n{task_obj}\n```"
    )


def build_multitask_prompt(task_objs: list) -> str:
    """Build a prompt for multi-task workflow analysis using the live schema context.

    Parameters
    ----------
    task_objs : list
        The list of task objects to analyze.

    Returns
    -------
    str
        Formatted analysis prompt.
    """
    return (
        f"{BASE_ROLE}\n\n"
        f"{_build_data_schema_prompt()}\n\n"
        "Your job is to analyze a list of task objects to identify patterns across tasks, anomalies, relationships, "
        "or correlations between inputs, outputs, resource usage, duration, and task placement. "
        "Correlations involving 'used' vs 'generated' data are especially important. "
        "So are relationships between (used or generated) data and resource metrics. "
        "Try to infer the purpose of the workflow. "
        "Highlight outliers or critical tasks and give actionable insights or recommendations. "
        "Use the data provided to justify your analysis.\n\n"
        f"Task objects:\n```json\n{task_objs}\n```"
    )
