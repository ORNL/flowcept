# Flowcept Agent

This package contains the Flowcept MCP server, client helpers, data-query tools,
MCP-wrapper tools, prompts, context manager, and LLM infrastructure.

For code-assistant behavior, use the repository root `AGENTS.md`. Runtime usage
docs live in `docs/agent.rst`.

## Directory Layout

```
agents/
  context_manager.py         # FlowceptAgentContextManager, mcp_flowcept, get_df_context
  tool_result.py             # ToolResult Pydantic model (2xx/3xx/4xx/5xx conventions)

  llm/
    builders.py              # build_llm_model(), normalize_message()
    providers/
      claude_gcp.py          # ClaudeOnGCPLLM (Vertex AI)
      gemini25.py            # Gemini25LLM

  chat_orchestration/
    chat_orchestrator_service.py  # LangGraph + MemorySaver chat turn orchestration

  provenance_schema_manager/
    static_schema_builder.py # SCHEMA_CONTEXT, build_schema_context, assert_schema_documented
    dynamic_schema_tracker.py # Tracks evolving task/object schemas from live messages

  data_query_tools/          # Plain-Python tool cores — NO MCP imports
    db_query_tools.py        # query_tasks, query_workflows, get_task_summary, …
    in_memory_task_query_tools.py   # run_df_query, generate_result_df, …
    in_memory_workflow_query_tools.py  # execute_generated_workflow_query, run_workflow_query
    pandas_utils.py          # safe_execute, normalize_output, format_result_df, …

  mcp/
    mcp_server.py            # MCP server entry point (start with `flowcept --start-agent`)
    mcp_client.py            # Client helpers: run_tool(), run_prompt()
    mcp_tools/               # Thin MCP wrappers over data_query_tools/
      db_query_mcp_tools.py
      in_memory_task_query_mcp_tools.py
      in_memory_workflow_query_mcp_tools.py
      session_tools.py       # check_liveness, check_llm, record_guidance, prompt_handler, …
      report_tools.py        # generate_workflow_card

  prompts/
    README.md                # Prompt authoring rules
    base_prompts.py          # BASE_ROLE, build_single_task_prompt, build_multitask_prompt
    db_query_prompts.py      # build_db_filter_prompt
    in_memory_task_query_prompts.py   # Pandas code / plot prompt builders
    in_memory_workflow_query_prompts.py  # Workflow message query prompt builders
    chat_prompts.py          # Webservice chat system prompt
    mcp_prompts.py           # @mcp_flowcept.prompt() registrations
```

## One Agent, Two Orchestrators

Both paths share the same MCP server, context, tools, prompts, and execution
functions. The difference is who does routing and LLM reasoning:

- **Internal LLM mode** (`external_llm: false`): Flowcept builds the configured
  LLM and orchestrates via `prompt_handler`.
- **External LLM mode** (`external_llm: true`): Claude Code, Codex, LibreChat,
  or another assistant calls MCP prompt-builders and execution tools directly.

## Schema Context

`SCHEMA_CONTEXT` (module-level dict in `provenance_schema_manager/static_schema_builder.py`) is populated at
MCP server startup via `build_schema_context()`. It maps:

```python
{
  "task_fields": [...],            # TaskObject attribute docs
  "workflow_fields": [...],        # WorkflowObject attribute docs
  "telemetry_summary_fields": [...],  # TelemetrySummary + subclass docs
  ...
}
```

All prompt builders in `prompts/` use `SCHEMA_CONTEXT` for field tables instead
of hardcoded strings. The MCP server refuses to start if any non-private field
is undocumented (`SchemaDocumentationError`).

## Equivalent Tool Paths

| Capability | Internal | External |
|---|---|---|
| Task DF question | `prompt_handler("t: ...")` | `build_df_query_prompt` → LLM → `execute_generated_df_code` |
| Object DF question | `prompt_handler("o: ...")` | same, `context_kind="objects"` |
| Workflow question | `prompt_handler("w: ...")` | `build_workflow_query_prompt` → LLM → `execute_generated_workflow_query` |
| DB provenance | `query_tasks` / `query_workflows` | same tools |
| Reports | `generate_workflow_card` | same tool |

## PROV-AGENT Instrumentation

Flowcept tracks AI agent provenance following the **PROV-AGENT** model
(arXiv:2508.02866), a W3C PROV extension for agentic workflows.
Two `subtype` values from `flowcept.commons.vocabulary.PROV_AGENT` identify
agent-specific activities in the task database:

| Enum | Stored string | What it captures |
|---|---|---|
| `PROV_AGENT.AI_MODEL_INVOCATION` | `"ai_model_invocation"` | One LLM prompt → response call |
| `PROV_AGENT.AGENT_TOOL` | `"agent_tool"` | One tool execution by an AI agent |

### Automatic capture

**MCP tools** — every `@mcp_flowcept.tool()` function in `mcp_tools/` is also
decorated with `@agent_flowcept_task(subtype=PROV_AGENT.AGENT_TOOL)`.  No extra
code needed; tool calls are stored automatically when the interceptor is running.

**LLM calls** — wrap any LangChain model with `FlowceptLLM` to record every
`.invoke()` as `PROV_AGENT.AI_MODEL_INVOCATION`:

```python
from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM
wrapped = FlowceptLLM(llm, agent_id=my_agent_id)
response = wrapped.invoke("How many tasks failed?")
```

**LangGraph chat** — `run_chat` in `webservice/services/chat_orchestrator_service.py`
wraps each graph execution in a `Flowcept` context (`workflow_name="langgraph_chat"`,
`start_persistence=False`).  This gives every chat turn its own `workflow_id`.
Within the graph, `call_model` uses `FlowceptLLM` and `call_tools` uses
`FlowceptTask(subtype=PROV_AGENT.AGENT_TOOL)` — both inherit
`Flowcept.current_workflow_id` automatically.

### Querying agent provenance

```python
# All LLM calls by a specific agent
Flowcept.db.task_query(filter={"subtype": "ai_model_invocation", "agent_id": my_agent_id})

# All tool executions in a chat session (workflow)
Flowcept.db.task_query(filter={"subtype": "agent_tool", "workflow_id": thread_id})
```

The UI uses `subtype` to display AI agent workflows differently from regular
scientific workflow tasks.

See `docs/schemas.rst` → *PROV-AGENT and Flowcept* for the full data model and
paper reference.

## Starting the MCP Server

```bash
flowcept --start-agent
```

## Client Usage

```python
from flowcept.agents.mcp.mcp_client import run_tool, run_prompt

# Call a tool
result = run_tool("prompt_handler", kwargs={"message": "t: top 5 slowest activities"})

# Use a prompt builder (external LLM mode)
prompt = run_prompt(
  "build_df_query_prompt",
  args={"query": "top 5 slowest activities", "context_kind": "tasks"},
)
```
