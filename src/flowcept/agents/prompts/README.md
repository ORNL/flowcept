# Agents Prompts

This directory contains all prompt builder functions for the Flowcept agent subsystem.

## Files

| File | Purpose |
|---|---|
| `base_prompts.py` | `BASE_ROLE`, `build_single_task_prompt`, `build_multitask_prompt` — schema-aware analysis prompts using `SCHEMA_CONTEXT` |
| `db_query_prompts.py` | `build_db_filter_prompt` — generates Mongo-style filter JSON for DB queries |
| `in_memory_task_query_prompts.py` | Prompt builders for in-memory task DataFrame queries (`generate_pandas_code_prompt`, `generate_plot_code_prompt`, etc.) |
| `in_memory_workflow_query_prompts.py` | Prompt builders for querying the active workflow message object |
| `general_prompts.py` | Routing and small-talk prompts; `ROUTING_PROMPT`, `SMALL_TALK_PROMPT` |
| `chat_prompts.py` | System prompt for the webservice chat endpoint |

## Design Rules

1. **No MCP imports** — prompt files must never import `mcp_flowcept` or `FastMCP`.
   - The `@mcp_flowcept.prompt()` registrations live in `prompts/mcp_prompts.py`.

2. **Schema from SCHEMA_CONTEXT** — prompt builders that need field names or types must
   use `SCHEMA_CONTEXT` from `schema_introspection.py`, not hardcoded strings.
   `SCHEMA_CONTEXT` is populated at MCP server startup and is a module-level dict.

3. **Naming convention** — all public builder functions are named `build_*_prompt`.

4. **No side effects** — functions are pure builders; they never call LLMs or make DB queries.
