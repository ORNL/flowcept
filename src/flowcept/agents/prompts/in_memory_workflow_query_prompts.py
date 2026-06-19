# flake8: noqa: E501
"""Prompt builders for querying the active workflow message object."""

from __future__ import annotations

import json
from typing import Any


EMPTY_WORKFLOW_MESSAGE = "Current workflow_msg_obj is empty or null."


def _flatten_paths(value: Any, prefix: str = "") -> list[str]:
    """Return dot paths for nested dict/list values."""
    if isinstance(value, dict):
        paths = []
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.append(child_prefix)
            paths.extend(_flatten_paths(child, child_prefix))
        return paths
    if isinstance(value, list):
        paths = []
        for idx, child in enumerate(value[:3]):
            child_prefix = f"{prefix}.{idx}" if prefix else str(idx)
            paths.append(child_prefix)
            paths.extend(_flatten_paths(child, child_prefix))
        return paths
    return []


def _example_values(workflow_msg_obj: dict, paths: list[str], limit: int = 60) -> dict:
    examples = {}
    for path in paths[:limit]:
        try:
            value = _resolve_path(workflow_msg_obj, path)
        except KeyError:
            continue
        if isinstance(value, (dict, list)):
            continue
        examples[path] = value
    return examples


def _resolve_path(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, list):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def build_workflow_query_prompt(query: str, workflow_msg_obj: dict, custom_user_guidance=None) -> str:
    """Build an LLM prompt that maps a free-text workflow question to field paths.

    Parameters
    ----------
    query : str
        Free-text question about the workflow.
    workflow_msg_obj : dict
        The live workflow message object.
    custom_user_guidance : list, optional
        Custom guidance strings.

    Returns
    -------
    str
        Formatted LLM prompt.
    """
    paths = _flatten_paths(workflow_msg_obj)
    examples = _example_values(workflow_msg_obj, paths)
    guidance = ""
    if custom_user_guidance:
        guidance = "\n".join(f"- {msg}" for msg in custom_user_guidance)
        guidance = f"\nUser guidance:\n{guidance}\n"

    return f"""
You are an expert in workflow provenance metadata.
The user has a JSON workflow message object called `workflow_msg_obj`.
Your job is to translate a free-text question into a strict JSON query spec.

AUTHORITATIVE FIELD PATHS:
{json.dumps(paths, indent=2, default=str)}

EXAMPLE SCALAR VALUES:
{json.dumps(examples, indent=2, default=str)}
{guidance}

Rules:
- Use only field paths from AUTHORITATIVE FIELD PATHS.
- Never invent fields or values.
- If the requested information is absent, include it under `missing`.
- For workflow description questions, use only an explicit description-like field if present. If none exists, mark it missing.
- Return only JSON. No markdown, no explanation.

Output format:
{{"field_paths": ["path.one", "path.two"], "missing": ["human-readable missing item"], "answer_style": "short"}}

Examples:
Q: what's the workflow name?
{{"field_paths": ["name"], "missing": [], "answer_style": "short"}}

Q: what was the settings path?
{{"field_paths": ["conf.settings_path"], "missing": [], "answer_style": "short"}}

Q: what's the workflow description?
{{"field_paths": [], "missing": ["workflow description"], "answer_style": "short"}}

Q: what hardware was used?
{{"field_paths": ["machine_info"], "missing": [], "answer_style": "summary"}}

User query:
{query}
"""
