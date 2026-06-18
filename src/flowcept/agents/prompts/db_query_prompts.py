# flake8: noqa: E501
"""Prompt builders for database provenance queries.

All functions are plain Python — no MCP framework imports.
"""

from flowcept.agents.schema_introspection import SCHEMA_CONTEXT

ALLOWED_FILTER_OPERATORS = frozenset(
    {
        "$and",
        "$or",
        "$nor",
        "$not",
        "$exists",
        "$eq",
        "$ne",
        "$gt",
        "$gte",
        "$lt",
        "$lte",
        "$in",
        "$nin",
        "$regex",
    }
)


def _build_task_field_list() -> str:
    """Return a bullet list of valid task field names from SCHEMA_CONTEXT."""
    fields = [f"`{f['name']}`" for f in SCHEMA_CONTEXT.get("task_fields", [])]
    fields += [f"`telemetry_summary.{f['name']}`" for f in SCHEMA_CONTEXT.get("telemetry_summary_fields", [])]
    return "\n".join(f"  - {name}" for name in fields) if fields else "  *(schema not yet loaded)*"


def build_db_filter_prompt(query: str, collection: str = "tasks") -> str:
    """Build a prompt that asks an LLM to generate a Mongo-style filter JSON for a DB query.

    Parameters
    ----------
    query : str
        Natural language question to translate into a filter.
    collection : str, optional
        Target collection name ("tasks" or "workflows").

    Returns
    -------
    str
        Formatted prompt.
    """
    return f"""You are an expert in MongoDB query construction for workflow provenance data.
The user wants to query the ``{collection}`` collection.

## Valid filter operators
Only these operators are allowed:
{", ".join(sorted(ALLOWED_FILTER_OPERATORS))}

## Valid field names
{_build_task_field_list()}

## Rules
- Use only field names from the list above.
- Use only operators from the allowlist.
- Do NOT invent field names or operators.
- Return only valid JSON — no markdown, no explanations.
- For missing information, return an empty filter: {{}}
- Date/time fields use Unix timestamps (seconds since epoch).

## Output format
Return a single JSON object (the filter). Example:
{{"activity_id": "train_model", "telemetry_summary.duration_sec": {{"$gt": 60}}}}

User query:
{query}
"""
