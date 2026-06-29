"""System prompt builder for the webservice provenance chat."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from flowcept.agents.chat_orchestration.tool_registry import (
    query_tasks,
    query_objects,
    query_workflows,
    list_agents,
    list_campaigns,
    get_task_summary,
    highlight_lineage,
    make_chart,
    get_dashboard,
    update_dashboard,
)
from flowcept.agents.prompts.base_prompts import build_common_chat_rules
from flowcept.agents.prompts.db_query_prompts import build_db_chat_rules
from flowcept.agents.prompts.df_query_prompts import build_df_chat_rules

_TASK_KEY_FIELDS = {
    "task_id",
    "activity_id",
    "workflow_id",
    "campaign_id",
    "agent_id",
    "status",
    "started_at",
    "ended_at",
    "used",
    "generated",
    "hostname",
    "tags",
    "parent_task_id",
    "telemetry_at_start",
    "telemetry_at_end",
}
_WORKFLOW_KEY_FIELDS = {"workflow_id", "name", "campaign_id", "user", "utc_timestamp"}
_BLOB_KEY_FIELDS = {"object_id", "object_type", "task_id", "workflow_id", "tags", "version"}


def _build_schema_section() -> str:
    """Build field descriptions from SCHEMA_CONTEXT; fall back to safe static text."""
    try:
        from flowcept.agents.provenance_schema_manager.static_schema_builder import (
            SCHEMA_CONTEXT,
            build_schema_context,
        )

        ctx = SCHEMA_CONTEXT if SCHEMA_CONTEXT else build_schema_context()
    except Exception:
        ctx = {}

    def _fmt(fields, key_set):
        parts = []
        for f in fields:
            if f["name"] in key_set:
                desc = f.get("description", "")
                parts.append(f"`{f['name']}`" + (f" ({desc})" if desc else ""))
        return ", ".join(parts) if parts else None

    task_line = _fmt(ctx.get("task_fields", []), _TASK_KEY_FIELDS)
    wf_line = _fmt(ctx.get("workflow_fields", []), _WORKFLOW_KEY_FIELDS)
    blob_line = _fmt(ctx.get("blob_fields", []), _BLOB_KEY_FIELDS)

    if task_line and wf_line and blob_line:
        return f"Key task fields: {task_line}.\nKey workflow fields: {wf_line}.\nKey object fields: {blob_line}."

    # fallback when SCHEMA_CONTEXT is not yet populated — derived from the key-field sets
    def _static(key_set):
        return ", ".join(f"`{n}`" for n in sorted(key_set))

    return (
        f"Key task fields: {_static(_TASK_KEY_FIELDS)}.\n"
        f"Key workflow fields: {_static(_WORKFLOW_KEY_FIELDS)}.\n"
        f"Key object fields: {_static(_BLOB_KEY_FIELDS)}."
    )


def _build_footer(schema_context: Optional[str], context: Optional[Dict[str, Any]]) -> str:
    """Build the trailing context block appended to every chat prompt."""
    parts = []
    if schema_context:
        parts.append(f"\nSchema context:\n{schema_context}\n")
    if context:
        parts.append(f"\nCurrent user context (scope queries with it): {json.dumps(context)}")
    return "".join(parts)


def build_chat_system_prompt(context: Optional[Dict[str, Any]] = None) -> str:
    """Build the system prompt for the webservice provenance chat."""
    context = dict(context or {})
    schema_context = context.pop("schema_context", None)
    tool_context_mode = context.get("tool_context", "db")
    schema_section = _build_schema_section()
    header = (
        "You are the Flowcept provenance assistant, embedded in Flowcept's web UI.\n"
        "Flowcept captures workflow provenance: campaigns group workflows; workflows contain tasks;\n"
        "tasks record used (inputs), generated (outputs), status, timings, telemetry, and host info;\n"
        "data objects (versioned binary artifacts) are stored separately with an object_type label.\n\n"
        + schema_section
        + "\n\n"
    )
    common_rules = build_common_chat_rules()

    if tool_context_mode == "df":
        query_rules = build_df_chat_rules(
            query_tasks.__name__,
            query_objects.__name__,
            list_agents_tool=list_agents.__name__,
            workflow_context_tool=query_workflows.__name__,
        )
    else:
        query_rules = build_db_chat_rules(
            query_tasks_tool=query_tasks.__name__,
            list_campaigns_tool=list_campaigns.__name__,
            list_agents_tool=list_agents.__name__,
            get_task_summary_tool=get_task_summary.__name__,
            highlight_lineage_tool=highlight_lineage.__name__,
            make_chart_tool=make_chart.__name__,
            get_dashboard_tool=get_dashboard.__name__,
            update_dashboard_tool=update_dashboard.__name__,
        )

    return header + common_rules + query_rules + _build_footer(schema_context, context)
