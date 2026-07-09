# `data_query_tools/`

Plain-Python query implementations shared by two LLM surfaces: the **MCP agent** (`mcp/mcp_tools/`) and the **webservice chat** (`chat_orchestration/`). No LangChain, no MCP framework, no Flask imports here — only business logic and `ToolResult` return values.

## Why this exists

Both the MCP server and the LangGraph chat loop need the same query logic. Putting it here once means neither surface has its own copy, so bugs are fixed once and behavior is consistent.

## Modules

### `base_query_tools.py`
Abstract base class (`BaseQueryTools`) that enforces symmetry between the DB and DF paths. Every method the chat agent may call is declared here as `@abstractmethod`. Shared concrete methods (`list_agents`, `list_campaigns`) live here and always delegate to the DB layer, since agent/campaign derivations are DB-only.

### `db_query_tools.py`
`DBQueryTools` — queries backed by MongoDB via `DBAPI`. Used when `tool_context == "db"`. Implements `query_tasks`, `query_workflows`, `get_task_summary`, `query_objects`, and related helpers. Results are normalized through `normalize_docs` and returned as `ToolResult`.

### `df_query_tools.py`
`DFQueryTools` — queries backed by an in-memory pandas DataFrame loaded from the MCP context. Used when `tool_context == "df"`. Implements `generate_result_df`, `generate_objects_df`, `generate_plot_code`, `extract_or_fix_python_code`, and `get_workflow_context`. LLM-generated pandas code is executed via `safe_execute`; errors trigger `query_runtime_retry`.

### `dashboard_tools.py`
Chart building and dashboard CRUD (`make_chart`, `get_dashboard`, `update_dashboard`). Path-agnostic (both DB and DF chat contexts can request charts). Persists chart specs to MongoDB and returns them for the UI to render.

### `pandas_utils.py`
Low-level pandas execution helpers used by `DFQueryTools`:
- `safe_execute(code, df)` — runs LLM-generated pandas code in a sandboxed `exec` environment (`{"df": df, "pd": pd, "np": np}`); enforces the `result = ...` convention.
- `normalize_output(result)` — coerces exec output to a DataFrame (lists → `{"List_Value": …}`, dicts → single-row DataFrame).
- `format_result_df(df)` — converts a DataFrame to a compact CSV string capped at 100 rows.
- `summarize_df(df, llm)` — optional LLM-assisted summary for large result sets.
- `load_saved_df`, `safe_json_parse`, `clean_code` — I/O and parsing helpers.

### `tools_utils.py`
`query_runtime_retry(execute_fn, fix_fn, max_attempts)` — shared retry loop. On a query runtime error (pandas exception or MongoDB `OperationFailure`), calls `fix_fn` to get a corrected callable and retries. Out of scope: parse errors, auth errors, network errors.

## Data flow

```
chat request
    └─► tool_registry.py  (LangChain tool wrappers)
            └─► db_query_tools.py  or  df_query_tools.py
                    └─► base_query_tools.py (shared interface)
                    └─► pandas_utils.py     (DF path only)
                    └─► tools_utils.py      (retry, both paths)
                    └─► dashboard_tools.py  (chart requests)
                    └─► ToolResult

MCP tool call
    └─► mcp/mcp_tools/db_query_mcp_tools.py   (thin @mcp.tool wrappers)
    └─► mcp/mcp_tools/df_query_mcp_tools.py
            └─► same db_query_tools.py / df_query_tools.py
```

Both surfaces call the same core functions; only the framework wrapper (LangChain vs MCP) differs.
