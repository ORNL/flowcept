# `prov_analysis/`

Agentic provenance analysis over Flowcept PROV-AGENT records. Pure-Python analysis functions shared by **four surfaces**: the harness MCP server (`agents/harness/mcp_server.py`), the Flowcept agent MCP server (`mcp/mcp_tools/analysis_mcp_tools.py`), the webservice chat (`chat_orchestration/tool_registry.py`), and the `flowcept-harness analyze` CLI subcommand.

## Why this exists

Every surface that can see provenance records — harness buffers, the agent's in-memory context, or the DB — needs the same analyses (what happened, what failed, what was slow, how agents behaved, how frameworks link). Putting the logic here once means all surfaces stay consistent, following the same layering rule as `data_query_tools/`: **cores are framework-free; MCP/LangChain wrappers are thin**.

## Modules

### `core.py`
Pure functions over `records: list[dict]` — a mixed list of workflow/task/agent records in either the harness-buffer shape (`agents/harness/prov.py`) or the framework-plugin shape (LangGraph, CrewAI, AutoGen, Academy). Dependency-light: stdlib plus `flowcept.report.aggregations` (itself stdlib-only), so the harness MCP server can import it lazily without pulling pandas or a backend. Fields that may be absent degrade gracefully.

- `load_records(jsonl_path=None, records=None, workflow_id=None, campaign_id=None)` — load from a JSONL buffer (via `report.loaders.read_jsonl`), pass records through, or (guarded, lazy) load from the Flowcept DB.
- `summarize_execution(records, workflow_id=None)` — counts by type/subtype/activity, duration bounds, status counts, campaigns/agents seen, token-usage totals (harness `custom_metadata.llm_usage` and plugin `generated.*_tokens` fields), and per-activity rows via `report.aggregations.group_activities`.
- `analyze_errors(records)` — failed tasks grouped by `activity_id` with stderr/message excerpts, error rate per activity, first/last failure times.
- `analyze_agent_behavior(records)` — per agent/session: turns, tool calls by tool, LLM calls, token usage, error counts, avg/max task durations; plus session workflows and subagent counts.
- `find_slowest_tasks(records, limit=10)` — slowest tasks with `task_id`, `activity_id`, `elapsed_seconds`, `status`, and parent-chain depth.
- `cross_framework_links(records)` — edges built from `source_agent_id` pointers (top-level, `custom_metadata.source_agent_id`, or `used`/`used.inputs._source_agent_id`): `{source_task_id, target_task_id, target_workflow_id, frameworks}`, plus the count of unlinked tasks.
- `compare_executions(records_a, records_b)` — per-activity count/duration/error-rate deltas between two executions.

### `tools.py`
`ToolResult` wrappers over each core function, following the `_guarded` convention of `data_query_tools` (3xx success dicts, 4xx error strings). Framework-free: no MCP or LangChain imports.

## Surfaces

```
harness MCP server (stdlib-only file; imports core lazily inside tools)
    analyze_session / analyze_errors / find_slowest / cross_links
        └─► prov_analysis.core           over the session's JSONL buffer

Flowcept agent MCP (mcp/mcp_tools/analysis_mcp_tools.py)
    df_summarize_execution, df_analyze_errors, df_agent_behavior,
    df_find_slowest, df_cross_framework_links   ── agent in-memory context
    db_* variants                               ── DBAPI workflow/task queries
    compare_executions(workflow_id_a, workflow_id_b)
        └─► prov_analysis.tools ─► prov_analysis.core

chat (chat_orchestration/tool_registry.py)
    StructuredTool wrappers routing df/db by tool_context, via run_mcp

CLI
    flowcept-harness analyze <session> [--errors | --slowest N | --links]
        └─► prov_analysis.core           over the session's JSONL buffer
```

## Record-shape notes

- Harness records carry `type: task|workflow|agent`, subtypes `ai_model_invocation` / `agent_tool` / `harness_event`, and token usage under `custom_metadata.llm_usage`.
- Framework-plugin records may omit `type` (they always carry `task_id`), use subtypes like `langgraph_graph|langgraph_node|llm_call|tool_call`, and put token usage in `generated.prompt_tokens|completion_tokens|total_tokens`.
- Cross-framework links travel as `custom_metadata.source_agent_id` (and the raw `_source_agent_id` inside `used.inputs`).
