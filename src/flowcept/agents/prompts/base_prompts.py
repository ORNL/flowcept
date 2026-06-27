# flake8: noqa: E501
"""Base prompt builders using SCHEMA_CONTEXT for schema-aware task analysis.

These replace the hardcoded schema strings in ``general_prompts.py`` with
live schema tables derived from ``SCHEMA_CONTEXT`` (populated at MCP server startup).
"""

from flowcept.agents.provenance_schema_manager.static_schema_builder import SCHEMA_CONTEXT

BASE_ROLE = (
    "You are a helpful assistant analyzing provenance data from a large-scale workflow composed of multiple tasks."
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


def build_common_chat_rules() -> str:
    """Return behavioral rules shared by all chat query paths (DB and DF)."""
    return (
        "General rules — apply to all query paths:\n"
        "- Mirror the user's vocabulary: use the user's exact question terms in your response —"
        " not just comparative adjectives ('highest', 'lowest') but also the key conceptual nouns"
        " they ask about. If the user asks about 'X', use the word 'X' when reporting whether X was found.\n"
        "- Always echo the exact numeric threshold and unit keywords from the user's question"
        " (e.g. 'files', '100', 'Mb', 'seconds') — even when data is unavailable."
        " Example: 'No input files larger than 100 Mb are tracked in this workflow.'\n"
        "- After generating a chart or plot, always summarize the key data values in your text"
        " response — e.g. 'A bar chart of tasks per activity: train_and_validate: 5 tasks.'."
        " Never respond with only 'the chart has been generated' without listing the actual values.\n"
        "- When asked about execution time, wall-clock time, or completion time: always express the"
        " answer in seconds — say 'X seconds' or 'execution time in seconds is not available'."
        " Never omit the word 'seconds'.\n"
        "- Be concise. Use markdown tables for tabular answers.\n"
        "- When reporting metadata, always use the exact field names from the returned record"
        " without renaming or paraphrasing them. Report field values verbatim.\n"
        "- Each record type has a distinct scope: use the appropriate query tool for each —"
        " never substitute one record type for another.\n"
        "- For questions about what a stored artifact IS (its purpose, type, properties, design),"
        " always use the artifact query tool — not the task or execution query tool.\n"
        "- Always use the provided tools to verify data before answering — never answer from"
        " memory or assumption, even if you believe the data is unavailable.\n"
        "- Receiving schema or structural information alone is never sufficient to answer a data"
        " question — always query the actual values.\n"
        "- Never invent values or infer answers from prior knowledge. Quote real numbers directly"
        " from tool results.\n"
        "- Refer to named entities by their human-readable labels — never output raw internal identifiers.\n"
        "- When enumerating discrete values, list ALL of them explicitly — never substitute a"
        " range or summary for the full list.\n"
        "- When multiple records share the same extreme value (tied highest or lowest), report"
        " ALL of them — never report only one.\n"
        "- When asked whether a specific type of activity occurred, check the actual records."
        " An activity occurred only if it appears explicitly in the provenance data —"
        " do not infer from timing, outcomes, or execution order.\n\n"
    )


_ANALYSIS_CORE = (
    "Correlations involving 'used' vs 'generated' data are especially important. "
    "So are relationships between (used or generated) data and resource metrics. "
    "Highlight outliers or critical information and give actionable insights or recommendations."
)


def _build_prompt(role_suffix: str, job: str, data_label: str, data) -> str:
    return (
        f"{BASE_ROLE}{role_suffix}\n\n"
        f"{_build_data_schema_prompt()}\n\n"
        f"{job} {_ANALYSIS_CORE}\n\n"
        f"{data_label}:\n```json\n{data}\n```"
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
    return _build_prompt(
        role_suffix=" You are focusing now on a particular task object.",
        job=(
            "Your job is to analyze this single task. Find any anomalies, relationships, or correlations between "
            "input, output, resource usage metrics, task duration, and task placement. "
            "Explain what this task may be doing, using the data provided."
        ),
        data_label="Task object",
        data=task_obj,
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
    return _build_prompt(
        role_suffix="",
        job=(
            "Your job is to analyze a list of task objects to identify patterns across tasks, anomalies, "
            "relationships, or correlations between inputs, outputs, resource usage, duration, and task placement. "
            "Try to infer the purpose of the workflow. "
            "Use the data provided to justify your analysis."
        ),
        data_label="Task objects",
        data=task_objs,
    )
