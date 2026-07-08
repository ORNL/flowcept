# flake8: noqa: E501
"""Shared schema prompt context for DB and runtime in-memory query paths."""

from typing import Any

from flowcept.agents.provenance_schema_manager.static_schema_builder import SCHEMA_CONTEXT


def build_allowed_fields_prompt(current_fields: list[str], target_name: str = "records") -> str:
    """Build the authoritative allowed-field constraint shared by query prompts."""
    return f"""
### ABSOLUTE FIELD CONSTRAINT -- THIS IS CRITICAL

The following list is the ONLY valid field names in {target_name}. Treat this as the schema:

ALLOWED_FIELDS = {current_fields}

You MUST treat this list as authoritative.

- You may only use field names that appear EXACTLY (string match) in ALLOWED_FIELDS.
- You are NOT allowed to create new field names by:
  - adding or removing prefixes like "used." or "generated."
  - combining words
  - guessing.
- If a field name is not in ALLOWED_FIELDS, you MUST NOT use it.
"""


def build_example_values_prompt(example_values: dict[str, Any]) -> str:
    """Build a domain-neutral example-value context block."""
    return f"""
Now, this dictionary provides type (t), up to 3 example values (v), and, for lists, shape (s) and element type (et) for each field.
Field names do not include `used.` or `generated.`. They represent the unprefixed form shared across roles. String values may be truncated if they exceed the length limit.
```python
{example_values}
```
"""


def build_task_static_field_table(current_fields: list[str]) -> str:
    """Build a markdown table of documented static task fields filtered to current fields."""
    rows = [
        "   | Column                        | Data Type | Description |",
        "   |-------------------------------|-----------|-------------|",
    ]
    for field in SCHEMA_CONTEXT.get("task_fields", []):
        if field["name"] in current_fields:
            rows.append(f"   | `{field['name']:<30}` | {field['type']:<9} | {field['description']} |")
    for field in SCHEMA_CONTEXT.get("telemetry_summary_fields", []):
        full_name = f"telemetry_summary.{field['name']}"
        if full_name in current_fields:
            rows.append(f"   | `{full_name:<30}` | {field['type']:<9} | {field['description']} |")
    if any(f.startswith("telemetry_summary.cpu") for f in current_fields):
        rows.append("   \n For any queries involving CPU, use fields that begin with telemetry_summary.cpu")
    return "\n".join(rows)


def build_task_structure_prompt(
    dynamic_schema: dict[str, Any],
    example_values: dict[str, Any],
    current_fields: list[str],
    record_description: str,
) -> str:
    """Build shared task schema context from observed dynamic schema and static field docs."""
    return f"""
## TASK RECORD STRUCTURE

{record_description}

### 1. Structured task fields:

- **in**: input parameters (fields starting with `used.`)
- **out**: output metrics/results (fields starting with `generated.`)

The schema below maps each activity ID to its inputs (i) and outputs (o), using flattened field names with `used.` or `generated.` prefixes. These names must match the allowed fields exactly.

{dynamic_schema}

Use this schema to understand what inputs and outputs are valid for each activity.

IMPORTANT: The user might use natural-language words such as "used" or "generated" loosely. Do not infer field names from those words. Always check ALLOWED_FIELDS and the activity schema.

### 2. Additional documented task fields:

{build_task_static_field_table(current_fields)}
---
{build_example_values_prompt(example_values)}
"""
