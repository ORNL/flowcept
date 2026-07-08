# `chat_orchestration/`

LangGraph-based chat loop that backs the `/api/v1/chat` webservice endpoint. The original monolith was split into four focused modules so each concern can be read, tested, and changed in isolation.

## Modules

### `chat_orchestrator_service.py`
Entry point and public API. Exposes `run_chat(...)` (returns a generator of token chunks or a final string) and `clear_chat_history(...)`. Owns:
- The `MAX_TOOL_ITERATIONS` guard (prevents infinite tool loops).
- `_CODE_RESPONSE_RE` — regex that detects when the LLM outputs Python code instead of a natural-language answer, triggering a rephrase call.
- The rephrase call itself: re-invokes the LLM with accumulated tool results and the user's original question.

Imports from the three modules below; contains no graph or tool logic itself.

### `graph_builder.py`
Builds and returns a compiled LangGraph `StateGraph`. Owns:
- `memory` — the module-level `MemorySaver` instance (shared across requests, keyed by `thread_id`).
- `_build_graph(llm, tools, ...)` — wires `agent` and `tools` nodes, sets routing via `should_continue`.
- `_enforce_first_tool` / `_tool_calls_for_text` — heuristic that forces the LLM's first message to be a specific tool call rather than a free-text answer. The heuristic matches query keywords to the right first tool (e.g. `generate_result_df` for task/activity/lineage questions, `get_workflow_context` for workflow metadata, `generate_objects_df` for model/artifact questions).
- Optional provenance instrumentation: when `INSTRUMENTATION_ENABLED` is set, tool calls are wrapped in `FlowceptTask` for lineage capture.

### `tool_registry.py`
Builds the list of LangChain `@tool`-decorated functions that the graph will use. Owns:
- `_build_langchain_tools(context, allow_dashboard_edit)` — wraps each MCP tool as a LangChain tool via thin closures over `run_tool(...)`. Selects the **DB tool set** or **DF tool set** based on `context["tool_context"]`.
- DB tools: `query_tasks`, `query_workflows`, `get_task_summary`, `list_campaigns`, `list_agents`, `make_chart`, `highlight_lineage`, `query_objects`.
- DF tools: `generate_result_df`, `generate_plot_code`, `extract_or_fix_python_code`, `get_workflow_context`, `list_agents`, `generate_objects_df`.

### `schema_context.py`
Context enrichment helpers called before each chat turn. Owns:
- `_with_workflow_schema_context(context)` — fetches the DB-backed workflow schema (field names, example values) and injects it into the context dict so the system prompt includes real field names.
- `_with_df_schema_context(context)` — fetches the in-memory DataFrame schema from the MCP server and injects it, giving the LLM accurate column names before it writes pandas code.

## Why this split

| Concern | Module |
|---|---|
| Conversation lifecycle, streaming, rephrase | `chat_orchestrator_service.py` |
| Graph topology, routing, first-tool heuristic, instrumentation | `graph_builder.py` |
| Tool surface (DB vs DF, tool signatures) | `tool_registry.py` |
| Schema injection into context | `schema_context.py` |

Keeping routing logic separate from tool definitions means you can add a new tool in `tool_registry.py` without touching the graph, and change routing heuristics in `graph_builder.py` without touching the wiring. Schema enrichment is isolated so it can be tested or mocked independently of the graph.
