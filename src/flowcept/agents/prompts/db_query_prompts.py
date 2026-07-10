# flake8: noqa: E501
"""Prompt builders for database provenance queries.

All functions are plain Python — no MCP framework imports.
"""

import json

from flowcept.agents.provenance_schema_manager.static_schema_builder import SCHEMA_CONTEXT, build_schema_context
from flowcept.agents.prompts.schema_prompt_context import (
    build_allowed_fields_prompt,
    build_task_structure_prompt,
)


def _build_task_field_list() -> str:
    """Return a bullet list of valid task field names from SCHEMA_CONTEXT."""
    fields = [f"`{f['name']}`" for f in SCHEMA_CONTEXT.get("task_fields", [])]
    fields += [f"`telemetry_summary.{f['name']}`" for f in SCHEMA_CONTEXT.get("telemetry_summary_fields", [])]
    return "\n".join(f"  - {name}" for name in fields) if fields else "  *(schema not yet loaded)*"


def _attribution_projection() -> str:
    """Return the task field set for attribution queries, derived from the live schema.

    Selects:
    - Identifier fields (names ending in ``_id``) that are core / non-optional,
      detected by the absence of "if any" or "nested" in their description.
    - Dict-typed IO fields whose description marks them as task inputs or outputs.
    - The execution-status field, detected by type name ``Status``.

    Because the list is built entirely from schema introspection, field renames in
    the domain class propagate automatically without changes to this function.
    """
    ctx = SCHEMA_CONTEXT if SCHEMA_CONTEXT else build_schema_context()
    fields = []
    for f in ctx.get("task_fields", []):
        name, type_str, desc = f["name"], f.get("type", ""), f.get("description", "").lower()
        is_core_id = name.endswith("_id") and "if any" not in desc and "nested" not in desc and "loop" not in desc
        is_io = type_str == "Dict" and ("inputs" in desc or "outputs" in desc)
        is_status = type_str == "Status"
        if is_core_id or is_io or is_status:
            fields.append(name)
    return json.dumps(fields) if fields else "[]"


def build_db_chat_rules(
    query_tasks_tool: str,
    list_campaigns_tool: str,
    list_agents_tool: str,
    get_task_summary_tool: str,
    highlight_lineage_tool: str,
    make_chart_tool: str,
    get_dashboard_tool: str,
    update_dashboard_tool: str,
) -> str:
    """Return the DB-mode chat rules block.

    All tool names are passed as parameters so that renames in the tool registry
    propagate here automatically rather than silently rotting as string literals.
    The attribution projection is derived from the live schema via
    :func:`_attribution_projection`, so field renames in the domain class are
    reflected without manual updates to this function.
    """
    proj = _attribution_projection()
    wf_id = next(
        (
            f["name"]
            for f in (SCHEMA_CONTEXT or build_schema_context()).get("workflow_fields", [])
            if f["name"].endswith("_id")
        ),
        "workflow_id",
    )
    campaign_id = next(
        (
            f["name"]
            for f in (SCHEMA_CONTEXT or build_schema_context()).get("task_fields", [])
            if "campaign" in f["name"]
        ),
        "campaign_id",
    )
    activity_id = next(
        (
            f["name"]
            for f in (SCHEMA_CONTEXT or build_schema_context()).get("task_fields", [])
            if "activity" in f["name"] and f["name"].endswith("_id")
        ),
        "activity_id",
    )
    return (
        "You have tools to query this data. Rules:\n"
        "- Use the tools to answer data questions.\n"
        "- Filters are Mongo-style; allowed operators: $and $or $nor $not $exists $eq $ne $gt $gte $lt"
        "  $lte $in $nin $regex. Never use $options — for case-insensitive regex use the inline flag:"
        '  {"field": {"$regex": "(?i)pattern"}}.\n'
        f"- When the user context includes {wf_id} or {campaign_id}, ALWAYS scope your queries with it.\n"
        f"- For campaigns: ALWAYS call `{list_campaigns_tool}` to get campaign details including the human-readable"
        "  campaign name. Never answer a campaign question from context alone — the context only has IDs.\n"
        f"- For workflows: when reporting any workflow result, ALWAYS include both the {wf_id}"
        "  raw value and the name field value explicitly, using their field labels. For a single"
        f'  result write: "{wf_id}: <id>, name: <name>". For multiple results use a markdown'
        "  table. Never omit either field.\n"
        f"- When answering about workflow activities, lineage, or execution order, use only {activity_id}"
        f"  values returned by provenance tools. Tool names are not workflow activities unless"
        f"  they explicitly appear as {activity_id} values in the returned provenance records.\n"
        f"- For agents: `{list_agents_tool}` returns agent identifier, human-readable name, activities, task_count.\n\n"
        "  Two patterns — choose based on the INTENT of the question, not what label appears in it:\n\n"
        "  PATTERN A — Question seeks the UPSTREAM DATA PRODUCER for a specific artifact or value:\n"
        "    Use EXACTLY 3 tool calls — no shortcuts:\n"
        f"    (1) Call `{get_task_summary_tool}` scoped to the workflow to discover activity names.\n"
        f"    (2) Call `{query_tasks_tool}` scoped to the workflow. Do NOT filter by the specific value —"
        "        you do not know which input or output field stores it. Include"
        f"        projection={proj}."
        "        Inspect BOTH input and output fields. If the value appears as output by one task"
        "        and input by another, the output-side task is the upstream producer.\n"
        f"    (3) Call `{list_agents_tool}` — MANDATORY for attribution. The task query returns raw"
        "        agent identifiers; only the agent listing tool maps them to human-readable names.\n"
        "    Write your final answer ONLY after all 3 calls complete."
        "    Write a direct factual statement using the user's question words and exact identifiers"
        "    from the data — do NOT write a summary paragraph or report unrelated tool results.\n\n"
        "  PATTERN B — MANDATORY ATTRIBUTION PROTOCOL — Triggered when the question asks WHO EXECUTED,\n"
        "    SUBMITTED, DISPATCHED, or ASSIGNED tasks for an activity (the VERB is the trigger, not what is named).\n"
        "    DOES trigger: 'Which agent submitted tasks for X?', 'Who dispatched X?', 'Which agent ran X?'.\n"
        "    DOES NOT trigger: 'What produced artifact Y?', 'What data fed into X?' — for those, use PATTERN A.\n"
        "    When triggered:\n"
        f"    Step 1 — Your FIRST tool call MUST be `{list_agents_tool}`. Do NOT make any other tool call first.\n"
        f"    Step 2 — Examine the returned agent-activity listing. Identify which agent ran the activity\n"
        "      associated with the target. If no agent directly ran the target activity, look for the agent\n"
        "      whose other activities are semantically related to submitting or dispatching that work.\n"
        f"    Step 3 — If the relationship is not yet clear, you may call `{get_task_summary_tool}` to\n"
        "      verify which activities ran in the workflow and derive attribution from both results.\n"
        f"    Do NOT call `{query_tasks_tool}` — task records do not contain explicit attribution links.\n"
        "    Report the agent name and its activity. Do NOT say 'not recorded' if agent activity data\n"
        "    provides a basis for attribution — derive the answer from what the agents ran.\n\n"
        "- For hardware/system questions: query task data.\n"
        f"- Prefer `{get_task_summary_tool}` for aggregate questions (counts, durations) over fetching all tasks."
        f"  When reporting task counts, include each {activity_id} and its count. Format as:"
        f"  'Activity A: N tasks, Activity B: M tasks, … Total: X tasks.'\n"
        "- For data lineage and data flow questions (including compound questions that mention"
        " 'lineage', 'all activities', 'execution order', or 'activities around X'):\n"
        f"  Do NOT call `{highlight_lineage_tool}` — it is a UI widget action only.\n"
        f"  Do NOT call `{query_tasks_tool}` — task-level details are not needed for lineage questions.\n"
        "  Use EXACTLY 2 tool calls — even when the question includes a qualifier like 'best', 'highest',"
        "  or names a specific task; the activity enumeration is always derivable from these two calls:\n"
        f"    (1) `{get_task_summary_tool}` — to see all activities and their counts.\n"
        f"    (2) `{list_agents_tool}` — to see which agent ran which activities.\n"
        "  Write your final answer ONLY after BOTH calls complete. Do NOT add extra calls.\n"
        f"- `{highlight_lineage_tool}` is ONLY for explicit UI highlight requests.\n"
        f"- When asked for a chart/plot, call `{make_chart_tool}` with a declarative chart spec:\n"
        '  {"chart_id": "<short-id>", "type": "chart", "title": "...",\n'
        '   "data": {"source": "tasks", "filter": {...}, "group_by": "<field>",\n'
        '            "metrics": [{"field": "<dot.path>", "agg": "avg|sum|min|max|count"}]},\n'
        '   "viz": {"kind": "bar|line|pie|scatter|area"}}\n'
        f"- To modify the user's dashboard (only when asked), call `{get_dashboard_tool}`, then"
        f"  `{update_dashboard_tool}` with the complete revised spec; explain what changed.\n"
        "- State filters you used.\n"
        "- IMPORTANT: after you receive tool results sufficient to answer the question, write your"
        "  FINAL ANSWER immediately — UNLESS you are in Pattern A or a lineage question, in which"
        "  case all required calls must complete before writing your answer.\n"
    )


def build_fix_query_prompt(query_params: dict, error: str) -> str:
    """Build a prompt asking the LLM to repair bad DB query parameters.

    Parameters
    ----------
    query_params : dict
        The original query parameters (filter, projection, sort, limit).
    error : str
        The error message produced when the query was attempted.

    Returns
    -------
    str
        Prompt string; the LLM must respond with a corrected JSON query_params object.
    """
    import json as _json

    return (
        "You are a MongoDB query repair assistant.\n"
        "The following query parameters caused a runtime error.\n\n"
        f"Original query_params:\n```json\n{_json.dumps(query_params, indent=2)}\n```\n\n"
        f"Error:\n{error}\n\n"
        "Return ONLY a corrected JSON object with the same keys (filter, projection, sort, limit). "
        "Do not include any explanation or markdown — raw JSON only."
    )


def build_db_schema_context(
    dynamic_schema: dict = None,
    example_values: dict = None,
    current_fields: list[str] = None,
) -> str:
    """Build shared schema context for database-backed query prompts."""
    if current_fields:
        context = build_allowed_fields_prompt(current_fields, target_name="database task records")
        if dynamic_schema is not None:
            context += build_task_structure_prompt(
                dynamic_schema=dynamic_schema,
                example_values=example_values or {},
                current_fields=current_fields,
                record_description="Each database task record represents one task.",
            )
        return context
    return "## Valid field names\n" + _build_task_field_list()
