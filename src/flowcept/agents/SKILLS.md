# Flowcept Agents Skill Guide (External LLM Only)

This guide is the operating contract for LLM orchestrators (for example, Codex) when this file is used.

## Mandatory Startup Workflow

After the user asks to read this `SKILLS.md`, always do this sequence:

1. Run `check_liveness` first.
2. If liveness fails, tell the user Flowcept Agent is not running and must be started in a separate terminal.
3. Provide the exact startup command (preferred env path):
   - `FLOWCEPT_SETTINGS_PATH=agent_sandbox/codex_tests_settings.yaml /Users/rsr/opt/miniconda3/envs/flowcept/bin/flowcept --start-agent`
4. Wait for the user to confirm the agent is running (or re-run liveness until success).
5. Once running, explicitly list the available agent tools before continuing with queries.

Do not proceed with DataFrame queries until liveness succeeds.

## Preferred Tool Invocation

Preferred method: use Flowcept CLI agent client, not raw Python.

- Use:
  - `FLOWCEPT_SETTINGS_PATH=agent_sandbox/codex_tests_settings.yaml /Users/rsr/opt/miniconda3/envs/flowcept/bin/flowcept --agent-client --tool-name <tool_name>`
- For tool arguments, pass JSON through `--kwargs`:
  - `... --agent-client --tool-name prompt_handler --kwargs '{"message":"result = df.head()"}'`

Only use raw Python `run_tool(...)` when CLI invocation is not possible.

Raw Python invocation guardrail:
- `run_tool()` accepts tool inputs only through the `kwargs` dictionary.
- Do **not** pass tool arguments as top-level kwargs to `run_tool` (for example, `query=...`).
- Correct pattern:
  - `run_tool("tool_name", kwargs={"arg_name": value}, host=..., port=...)`
- Incorrect pattern (causes `TypeError`):
  - `run_tool("tool_name", host=..., port=..., query="...")`

## Mode Contract

Always operate as if:

```yaml
agent:
  external_llm: true
```

Do not use or assume internal LLM routing/code generation behavior.
For Codex/sandbox bootstrap, use the dedicated scratch settings file with MQ enabled.

## Goal

Assistant role:
 You are a Helpful Provenance Query Assistant.
 Translate human provenance question

Use Flowcept agent tools to:
- inspect/query in-memory provenance context (`tasks`, schema, examples),
- run deterministic DataFrame commands,
- manage guidance memory (`@record`, `@show records`, `@reset records`),
- reset context safely.

Default preference: explicit, deterministic commands only.

## Primary Interfaces

- `flowcept.agents.agent_client.run_tool`
- `flowcept.agents.agent_client.run_prompt`
- `flowcept.agents.tools.general_tools`
  - `check_liveness`, `get_latest`, `check_llm`
  - `record_guidance`, `show_records`, `reset_records`, `reset_context`
  - `prompt_handler`
- `flowcept.agents.tools.in_memory_queries.in_memory_queries_tools`
  - `run_df_query`, `run_df_code`
  - `execute_generated_df_code`

## Required Orchestrator Behavior

Use explicit commands only:
- `save`
- `result = df ...`
- `run_prompt('build_df_query_prompt', ...)` + `execute_generated_df_code(...)`
- `@record ...`
- `@show records`
- `@reset records`
- reset context via explicit reset command/tool (`reset context` / `reset_context`)

Do not rely on free-form natural language routing for autonomous planning.

## Recommended Sequence

1. `check_liveness`
2. Optional: `get_latest`
3. Optional: `@record ...`
4. Run explicit DF command(s), for example `result = df[...]...`
5. Optional: `save`
6. If context is contaminated: reset context

External-LMM-friendly sequence:
1. `run_prompt('build_df_query_prompt', args={...})`
2. External LLM generates explicit pandas code (`result = df ...`)
3. `execute_generated_df_code(user_code=...)`

## Command Safety

Safe examples:
- `run_df_query(llm=<internal llm>, query="save")`
- `run_df_query(llm=<internal llm>, query="result = df[['a']].head()")`
- `run_tool("execute_generated_df_code", kwargs={"user_code": "result = df.head()"})`
- `run_prompt('build_df_query_prompt', ...); execute_generated_df_code(...)`
- `prompt_handler("@record prefer compact summaries")`
- `prompt_handler("reset context")`

Unsafe/blocked patterns:
- free-form NL expecting autonomous routing + generated pandas code,
- implicit planning via `prompt_handler`.
- `run_tool(..., query=...)` or any non-signature top-level kwarg for tool arguments.

## ToolResult Semantics

- 2xx: success, string payload
- 3xx: success, dict payload
- 4xx/5xx: error

405-like responses generally indicate explicit code/command is required.

## Transport Rules

Use `streamable-http` only:

1. `streamable-http`
   - requires reachable `http://<host>:<port>/mcp`,
   - requires explicit MCP server startup in selected environment.

## Day-1 Bootstrap (Zero Memory)

Always use this settings path when invoking agent tools:
- `FLOWCEPT_SETTINGS_PATH=agent_sandbox/codex_tests_settings.yaml`

First ensure the scratch directory exists:
- `mkdir -p agent_sandbox`

If `agent_sandbox/codex_tests_settings.yaml` does not exist, create it first.
Source of truth reference: `resources/sample_settings.yaml` (copy only required keys).

Minimal scratch file required for Codex agent mode (`external_llm=true`):

```yaml
project:
  db_flush_mode: online

log:
  log_file_level: disable
  log_stream_level: disable

telemetry_capture: {}

mq:
  enabled: true
  type: redis
  host: localhost
  port: 6379

kv_db:
  enabled: true
  host: localhost
  port: 6379

databases:
  mongodb:
    enabled: false
  lmdb:
    enabled: false

agent:
  external_llm: true
  mcp_host: 127.0.0.1
  mcp_port: 8000
```

If servers are not local, you must ask the user to provide routes to external services like Redis.

Why this is required:
- Satisfies the external-agent contract that requires MQ.
- Ensures campaign/context coordination via MQ + KVDB.
- Avoids telemetry permission failures in restricted environments (`telemetry_capture: {}`).

Prerequisite:
- Redis must be reachable at `localhost:6379` (or adjust `mq.host`/`kv_db.host` and ports accordingly).

Codex troubleshooting note:
- If MQ access fails from a Codex sandbox session, use workspace-write mode with network enabled in
  `~/.codex/config.toml`:

```toml
[sandbox_workspace_write]
network_access = true
```

Canonical liveness command:

```bash
FLOWCEPT_SETTINGS_PATH=agent_sandbox/codex_tests_settings.yaml \
/Users/rsr/opt/miniconda3/envs/flowcept/bin/python -u -c \
"from flowcept.agents.agent_client import run_tool; print(run_tool('check_liveness', host='127.0.0.1', port=8000))"
```

Expected response payload contains:
- `\"code\": 200`
- `\"result\": \"I'm FlowceptAgent and I'm ready!\"`
- `\"tool_name\": \"check_liveness\"`

## Environment Resolution Rules

- Do not install `flowcept` during environment resolution.
- If no valid Flowcept environment is found:
  - state that clearly,
  - ask the user which environment to use,
  - wait for user input before continuing.
- If Flowcept is detected in multiple environments/locations:
  - list all detected options,
  - ask the user to disambiguate,
  - wait for user input before continuing.

## Prompting Guidance for DF Commands

- Assign final output to `result` for code execution branches.
- Keep commands minimal and deterministic.
- Avoid side effects unless explicitly requested.

## Internal vs External LLM Paths

Internal LLM path:
1. Call `run_df_query(llm=<internal llm>, query=<natural language>)`
2. Agent generates pandas code internally (`generate_result_df`)
3. Agent executes and returns result

External LLM path (preferred in `external_llm=true`):
1. Call MCP prompt `build_df_query_prompt` via `run_prompt(...)`
2. External LLM reads prompt and generates pandas code (`result = df ...`)
3. Call `execute_generated_df_code(user_code=...)`
4. Agent executes code and returns result

## Mission Priorities

- Reproducibility
- Explicit behavior
- Minimal changes and code reuse
- No hidden orchestration behavior

## User Interaction

MANDATORY DISPLAY RULE:
- After reading this `SKILLS.md`, the assistant MUST display the `TL;DR for Users` block below.
- If the user asks things like "what can you do?", "how do I use this?", or "what tools can I run?", the assistant MUST display the same `TL;DR for Users` block again.
- Do not display internal sections by default.

MANDATORY `q:` PROTOCOL (RIGID, NO EXCEPTIONS):
- If message matches `q: <text>`, the assistant MUST execute this exact sequence in order:
1. `run_prompt('build_df_query_prompt', args={'query': '<text>'})`
2. Generate explicit deterministic pandas code with final assignment to `result`
3. `execute_generated_df_code(user_code=...)`
- The assistant MUST NOT skip, reorder, or replace steps.
- The assistant MUST NOT use direct handwritten DF execution for `q:` without step 1.
- If any step fails, STOP immediately, report failed step + error, and do not continue.

MANDATORY PROVENANCE CARD RULE:
- For provenance card generation requests, the assistant MUST use MCP tool `generate_workflow_provenance_card` only.
- The assistant MUST NOT use any fallback path (DB/report service, local Python, or other tools).
- If the MCP tool is unavailable/fails, STOP and report the MCP tool error only.
- On MCP success, the assistant MUST display the FULL markdown content in the chat response (no truncation, no summary-only output).


### TL;DR for Users

Use this format:

`q: <your provenance question>`

Examples:
- `q: show latest tasks`
- `q: what are the top 5 slowest activities?`
- `q: show input and output arguments for the last 3 tasks`

Only if needed:

- `get_latest`: quick context sanity check before first query.
- `reset_context`: recover from stale/noisy context.
- `query_on_saved_df`: offline/replay queries from persisted files.
- `generate_workflow_provenance_card`: generate a markdown provenance card for a specific workflow id.
