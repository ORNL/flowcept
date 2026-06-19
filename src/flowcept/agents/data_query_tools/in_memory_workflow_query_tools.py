"""Plain-Python in-memory workflow query tools.

Functions operate on a ``workflow_msg_obj`` dict (live MQ stream).
No MCP framework imports (``@mcp_flowcept.tool()`` lives in
``mcp_tools/in_memory_workflow_query_mcp_tools.py``).
"""

from __future__ import annotations

import json
from typing import Any

from flowcept.agents.tool_result import ToolResult
from flowcept.agents.llm.builders import build_llm_model

from flowcept.agents.prompts.in_memory_workflow_query_prompts import (
    EMPTY_WORKFLOW_MESSAGE,
    build_workflow_query_prompt,
)

MISSING_INFO = "info not available"


def _resolve_path(value: Any, path: str) -> Any:
    """Resolve a dot-separated path against a nested dict/list.

    Parameters
    ----------
    value : Any
        Root object to traverse.
    path : str
        Dot-separated field path (e.g. ``"conf.settings_path"``).

    Returns
    -------
    Any
        The value at the given path.

    Raises
    ------
    KeyError
        When a path segment is not found.
    """
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                raise KeyError(path)
            current = current[part]
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                raise KeyError(path)
        else:
            raise KeyError(path)
    return current


def _parse_query_spec(query_spec: dict | str) -> dict:
    """Parse a query spec dict or JSON string.

    Parameters
    ----------
    query_spec : dict or str
        A workflow query spec.

    Returns
    -------
    dict
    """
    if isinstance(query_spec, dict):
        return query_spec
    return json.loads(query_spec)


def _format_answer(values: dict, missing: list[str], answer_style: str) -> str:
    if not values and missing:
        return MISSING_INFO
    if answer_style == "summary":
        return json.dumps({"values": values, "missing": missing}, indent=2, default=str)
    if len(values) == 1 and not missing:
        return str(next(iter(values.values())))
    return json.dumps({"values": values, "missing": missing}, indent=2, default=str)


def execute_generated_workflow_query(query_spec: dict | str, workflow_msg_obj: dict) -> ToolResult:
    """Execute a workflow query spec against a workflow_msg_obj.

    The spec is JSON with ``field_paths`` and optional ``missing`` /
    ``answer_style`` fields. Missing values always return ``info not available``.

    Parameters
    ----------
    query_spec : dict or str
        Workflow query spec.
    workflow_msg_obj : dict
        The live workflow message object.

    Returns
    -------
    ToolResult
    """
    if not workflow_msg_obj:
        return ToolResult(code=404, result=EMPTY_WORKFLOW_MESSAGE)

    try:
        spec = _parse_query_spec(query_spec)
    except Exception as e:
        return ToolResult(code=405, result=f"Invalid workflow query spec: {e}")

    field_paths = spec.get("field_paths") or []
    missing = list(spec.get("missing") or [])
    answer_style = spec.get("answer_style", "short")
    values = {}

    for path in field_paths:
        try:
            values[path] = _resolve_path(workflow_msg_obj, path)
        except KeyError:
            values[path] = MISSING_INFO

    result = {
        "answer": _format_answer(values, missing, answer_style),
        "values": values,
        "missing": missing,
        "query_spec": spec,
    }
    return ToolResult(code=301, result=result, tool_name="execute_generated_workflow_query")


def run_workflow_query(query: str, workflow_msg_obj: dict, custom_user_guidance=None, llm=None) -> ToolResult:
    """Run a free-text query against the active workflow message object.

    Parameters
    ----------
    query : str
        Free-text question about the workflow.
    workflow_msg_obj : dict
        The live workflow message object.
    custom_user_guidance : list, optional
        Custom guidance strings.
    llm : callable, optional
        LLM callable. Built from settings if None.

    Returns
    -------
    ToolResult
    """
    if not workflow_msg_obj:
        return ToolResult(code=404, result=EMPTY_WORKFLOW_MESSAGE)

    if llm is None:
        llm = build_llm_model()

    prompt = build_workflow_query_prompt(query, workflow_msg_obj, custom_user_guidance)
    try:
        query_spec = llm(prompt)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=prompt)

    result = execute_generated_workflow_query(query_spec, workflow_msg_obj)
    result.extra = {"prompt": prompt}
    return result
