# Agents Prompts

This directory contains all prompt builder functions for the Flowcept agent subsystem.

## Files

| File | Purpose |
|---|---|
| `base_prompts.py` | `BASE_ROLE`, `build_single_task_prompt`, `build_multitask_prompt` — schema-aware analysis prompts using `SCHEMA_CONTEXT` |
| `db_query_prompts.py` | `build_db_schema_context` — shared DB schema context for query prompts |
| `df_query_prompts.py` | `build_pandas_code_prompt`, `build_plot_code_prompt`, … — in-memory DataFrame query prompt builders |
| `schema_prompt_context.py` | `build_allowed_fields_prompt`, `build_task_structure_prompt`, … — reusable field/schema prompt sections |
| `chat_prompts.py` | `build_chat_system_prompt` — system prompt builder for the webservice chat endpoint |

## Design Rules

1. **No MCP imports** — prompt files must never import `mcp_flowcept` or `FastMCP`.

2. **Schema from SCHEMA_CONTEXT** — prompt builders that need field names or types must
   use `SCHEMA_CONTEXT` from `schema_introspection.py`, not hardcoded strings.
   `SCHEMA_CONTEXT` is populated at MCP server startup and is a module-level dict.

3. **Naming convention** — all public builder functions are named `build_*_prompt`.

4. **No side effects** — functions are pure builders; they never call LLMs or make DB queries.
