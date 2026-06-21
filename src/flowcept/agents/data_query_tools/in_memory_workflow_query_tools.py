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
        response = llm.invoke(prompt)
        query_spec = response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=prompt)

    extraction = execute_generated_workflow_query(query_spec, workflow_msg_obj)
    if extraction.code >= 400:
        return extraction

    values = extraction.result.get("values", {}) if isinstance(extraction.result, dict) else {}
    missing = extraction.result.get("missing", []) if isinstance(extraction.result, dict) else []
    query_spec_used = extraction.result.get("query_spec", {}) if isinstance(extraction.result, dict) else {}

    nl_prompt = (
        f"Answer the following question in one or two concise sentences.\n"
        f"Use the field name verbatim (e.g., 'utc_timestamp') when referencing technical fields.\n\n"
        f"Question: {query}\n"
        f"Values: {json.dumps(values, default=str)}\n"
        f"Answer:"
    )
    try:
        nl_response = llm.invoke(nl_prompt)
        nl_answer = nl_response.content if hasattr(nl_response, "content") else str(nl_response)
    except Exception:
        nl_answer = (
            extraction.result.get("answer", str(extraction.result))
            if isinstance(extraction.result, dict)
            else str(extraction.result)
        )

    return ToolResult(
        code=301,
        result={
            "answer": nl_answer,
            "values": values,
            "missing": missing,
            "query_spec": query_spec_used,
        },
        tool_name="run_workflow_query",
        extra={"prompt": prompt},
    )
