"""MCP tools for querying the active workflow message object."""

from __future__ import annotations

import json
from typing import Any

from flowcept.agents.agents_utils import ToolResult, build_llm_model
from flowcept.agents.flowcept_ctx_manager import mcp_flowcept
from flowcept.agents.prompts.workflow_query_prompts import (
    EMPTY_WORKFLOW_MESSAGE,
    generate_workflow_query_prompt,
)

MISSING_INFO = "info not available"


def _resolve_path(value: Any, path: str) -> Any:
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


@mcp_flowcept.tool()
def execute_generated_workflow_query(query_spec: dict | str) -> ToolResult:
    """
    Execute an externally generated workflow query spec against workflow_msg_obj.

    The spec is JSON with ``field_paths`` and optional ``missing`` /
    ``answer_style`` fields. Missing values always return ``info not available``.
    """
    ctx = mcp_flowcept.get_context()
    workflow_msg_obj = ctx.request_context.lifespan_context.workflow_msg_obj
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
    return ToolResult(code=301, result=result, tool_name=execute_generated_workflow_query.__name__)


@mcp_flowcept.tool()
def run_workflow_query(query: str, llm=None) -> ToolResult:
    """
    Run a free-text query against the active workflow message object.

    This mirrors the DataFrame query flow but asks the LLM to select workflow
    message field paths instead of generating pandas code.
    """
    ctx = mcp_flowcept.get_context()
    workflow_msg_obj = ctx.request_context.lifespan_context.workflow_msg_obj
    if not workflow_msg_obj:
        return ToolResult(code=404, result=EMPTY_WORKFLOW_MESSAGE)

    if llm is None:
        llm = build_llm_model()

    prompt = generate_workflow_query_prompt(
        query,
        workflow_msg_obj,
        ctx.request_context.lifespan_context.custom_guidance,
    )
    try:
        query_spec = llm(prompt)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=prompt)

    result = execute_generated_workflow_query(query_spec)
    result.extra = {"prompt": prompt}
    return result
