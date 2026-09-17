# Flowcept Agents

This package contains everything agent-related in Flowcept:

1. **The Flowcept Agent** — the MCP server, client helpers, data-query tools,
   MCP-wrapper tools, prompts, context manager, and LLM infrastructure that let
   an LLM query provenance data. Runtime usage docs live in `docs/agent.rst`.
2. **Agentic framework provenance plugins** — zero-code-change capture of
   agent/action/LLM-call provenance from Academy, LangGraph, CrewAI, and
   AutoGen. Docs: `docs/agent_plugins.rst`.
3. **AI coding harness provenance plugins** — PROV-AGENT capture of coding
   sessions from Claude Code, other CLI harnesses (Codex, Gemini, Cursor,
   OpenCode), the Claude Agent SDK, the OpenAI Agents SDK,
   LangChain/LangGraph callbacks, and OpenTelemetry GenAI spans. Docs:
   `docs/harness_plugins.rst` and [`harness/README.md`](harness/README.md).

For code-assistant behavior, use the repository root `AGENTS.md`.

## What Lives Here

### Flowcept Agent (MCP server + web chat)

- `chat_orchestration/`: LangChain / LangGraph orchestration for the web chat.
  This is where the chat runtime, tool routing, and turn-level orchestration live.
  It should stay separate from HTTP route handlers.
- `mcp/`: the standalone MCP server surface. Keep these wrappers thin. They should
  load context, call tools, and return `ToolResult`, but not own business logic.
- `mcp/mcp_tools/`: MCP wrappers around shared tool cores. These are the public MCP
  entry points that external assistants call.
- `data_query_tools/`: shared query logic. This is where task, workflow, object, and
  DataFrame query behavior lives. These modules can call `DBAPI` for persisted data
  or read the in-memory DataFrame / workflow object for runtime questions.
- `prov_analysis/`: agentic provenance analysis over PROV-AGENT records — pure
  analysis functions (summaries, errors, agent behavior, slowest tasks,
  cross-framework links, run comparison) shared by the harness MCP server, the
  Flowcept agent MCP server, the web chat, and `flowcept-harness analyze`.
  Full docs: [`prov_analysis/README.md`](prov_analysis/README.md).
- `prompts/`: prompt-builder functions and prompt registrations. Keep them as plain
  Python builders that return strings, not Jinja templates.
- `provenance_schema_manager/`: schema introspection and documentation context used by
  prompt builders.
- `llm/`: model construction and normalization helpers. Centralize LLM creation here.
- `gui/`: legacy UI helpers. Do not extend this unless the old GUI is being revived.

### Agentic framework provenance plugins

Each plugin captures intra-agent, inter-agent, and LLM-call provenance from a
framework with zero code changes. They can be auto-started from the `plugins:`
block in `settings.yaml` (kinds: `academy`, `langgraph`, `crewai`, `autogen`)
or constructed directly; all four can share one `campaign_id` via
`from_academy_plugin()`. Each module also exports `openai_chat`,
`anthropic_chat`, and `FlowceptAnthropicClient` LLM-call wrappers.

- `academy/`: `FlowceptAcademyPlugin` — wraps Academy agents; records
  `academy_action` / `academy_loop` / `academy_lifecycle` tasks and nested
  `llm_call` records.
- `autogen/`: `FlowceptAutoGenPlugin`, `run_team()`, `FlowceptModelClient` —
  records `autogen_run` → `autogen_message` → `llm_call`.
- `crewai/`: `FlowceptCrewAIPlugin` — records `crewai_crew`, `crewai_task` →
  `crewai_agent` → `llm_call` / `tool_call` via CrewAI listeners/hooks.
- `langgraph/`: `FlowceptLangGraphPlugin` — records `langgraph_graph` →
  `langgraph_node` → `llm_call` / `tool_call` through `plugin.callback_handler`.

Docs: `docs/agent_plugins.rst`. Runnable examples: `examples/agents/`
(`academy/`, `langgraph/`, `crewai/`, `autogen/`,
`combined_agentic_systems/`).

### AI coding harness provenance plugins

Shared capture core plus one adapter module per source. The capture path is
stdlib-only and buffers JSONL per session under `~/.flowcept/harness/buffers/`;
inspect with the `flowcept-harness` CLI (`sessions`, `show`, `status`,
`report`, `flush`, `repair`, `install`, `hook`).

- `harness/`: the shared capture core — events, recorder, PROV-AGENT record
  constructors, JSONL buffers, `SessionTracer` for agents you write yourself,
  the `flowcept-harness` CLI (`harness/cli.py`), and the
  `flowcept-harness-mcp` server. Full docs: [`harness/README.md`](harness/README.md).
- `claude_code/`: Claude Code hook adapter (used by the `plugins/flowcept`
  Claude Code plugin, or by hooks in `settings.json`).
- `cli_harness/`: profile-driven adapter for other CLI harnesses;
  `profiles/` ships `codex`, `gemini`, `cursor`, `opencode` JSON profiles.
- `claude_agent_sdk/`: `trace_query` — a drop-in for `claude_agent_sdk.query`
  (`pip install "flowcept[harness_claude_sdk]"`).
- `openai_agents/`: `FlowceptTraceProcessor` + `install()` — a tracing
  processor for the OpenAI Agents SDK.
- `langchain/`: `FlowceptCallbackHandler` — a LangChain / LangGraph callback
  handler that records turns, model calls, and tool calls.
- `otel/`: `FlowceptSpanExporter` and `ingest_file()` for OpenTelemetry GenAI
  spans (`pip install "flowcept[harness_otel]"`).

Docs: `docs/harness_plugins.rst`. Example:
`examples/agents/harness/harness_example.py`.

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
    base_query_tools.py      # BaseQueryTools ABC (DB and DF path contract)
    db_query_tools.py        # DBQueryTools + query_tasks, query_workflows, get_task_summary, …
    df_query_tools.py        # DFQueryTools + run_df_query, execute_df_code, generate_result_df, …
    pandas_utils.py          # safe_execute, normalize_output, format_result_df, …

  prov_analysis/             # Pure provenance-analysis functions shared by all surfaces
    core.py                  # summarize_execution, analyze_errors, find_slowest_tasks, …
    tools.py                 # ToolResult wrappers over core (no MCP/LangChain imports)

  mcp/
    mcp_server.py            # MCP server entry point (start with `flowcept --start --agent`)
    mcp_client.py            # Client helpers: run_tool()
    mcp_tools/               # Thin MCP wrappers over data_query_tools/
      db_query_mcp_tools.py
      df_query_mcp_tools.py  # run_df_query (pure executor), execute_generated_df_code
      schema_mcp_tools.py    # get_workflow_schema_context, get_df_schema_context
      session_tools.py       # check_liveness, check_llm, record_guidance, reset_context, …
      report_tools.py        # generate_workflow_card
    mcp_prompts.py           # (empty — no MCP prompts registered)

  prompts/
    README.md                # Prompt authoring rules
    base_prompts.py          # BASE_ROLE, build_single_task_prompt, build_multitask_prompt
    db_query_prompts.py      # build_db_schema_context
    df_query_prompts.py      # build_pandas_code_prompt, build_plot_code_prompt, …
    chat_prompts.py          # build_chat_system_prompt() for the webservice chat

  # Agentic framework provenance plugins (docs/agent_plugins.rst)
  academy/                   # FlowceptAcademyPlugin
  autogen/                   # FlowceptAutoGenPlugin, run_team()
  crewai/                    # FlowceptCrewAIPlugin
  langgraph/                 # FlowceptLangGraphPlugin

  # AI coding harness provenance plugins (docs/harness_plugins.rst)
  harness/                   # shared capture core, SessionTracer, flowcept-harness CLI, MCP server
  claude_code/               # Claude Code hook adapter
  cli_harness/               # profile-driven adapter (+ profiles/: codex, gemini, cursor, opencode)
  claude_agent_sdk/          # trace_query wrapper
  openai_agents/             # OpenAI Agents SDK tracing processor
  langchain/                 # LangChain / LangGraph callback handler
  otel/                      # OTel GenAI span exporter and ingest
```

## One Agent, Two Orchestrators

The MCP agent exposes explicit tools. Claude Code, Codex, LibreChat, or another
assistant can call MCP prompt-builders and execution tools directly.

The webservice chat path is the sister module that owns the HTTP-facing chat UI.
Its route layer stays thin and delegates to the chat orchestrator in
`src/flowcept/webservice/services/`. That orchestrator calls into the same shared
tool cores used by the MCP surface.

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
| Task DF question | `run_df_query(code=...)` | `get_df_schema_context` → LLM generates code → `run_df_query(code=...)` |
| Object DF question | `run_df_query(code=..., context_kind="objects")` | same, `context_kind="objects"` |
| DB provenance | `query_tasks` / `query_workflows` | same tools |
| DB schema context | `get_workflow_schema_context` | same tool |
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

**LangGraph chat** — `run_chat` in `chat_orchestration/chat_orchestrator_service.py`
wraps each graph execution in a `Flowcept` context (`workflow_name="Flowcept LangGraph Chat"`,
`start_persistence=True`).  This gives every chat turn its own `workflow_id`.
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
flowcept --start --agent
```

## Client Usage

```python
from flowcept.agents.mcp.mcp_client import run_tool, run_prompt

# Get schema context (external LLM mode)
schema = run_tool("get_df_schema_context", kwargs={"context_kind": "tasks"})

# Execute generated pandas code
result = run_tool("run_df_query", kwargs={"code": "result = df.groupby('activity_id').size()", "context_kind": "tasks"})
```
