# Flowcept Agents: External LLM Usage (Step by Step)

This guide explains how to use Flowcept Agents with an external LLM orchestrator
(for example, Codex), using `SKILLS.md` as the operating contract.

## 1) Enable external mode

Set in your Flowcept settings:

```yaml
agent:
  external_llm: true
```

This disables internal LLM routing/code generation paths used by agent tools.

## 2) Start the Flowcept agent (MCP server)

Run:

```bash
python -m flowcept.agents.flowcept_agent
```

or, preferably, via Flowcept CLI:

```bash
flowcept --start-agent
```

Important:
- Run this command from a Python environment where Flowcept is installed.
- In this repository, prefer the project conda env that contains the Flowcept package.
- If needed, call the env-specific binary directly, e.g.:
  `/path/to/env/bin/flowcept --start-agent`

## 2.1) Transport choice (important)

- Client transport is HTTP (`streamable-http`) and requires reachable
  `http://<host>:<port>/mcp`.

## 3) Load the skills contract

Before orchestrating tools, read:

```text
src/flowcept/agents/SKILLS.md
```

That file defines allowed patterns, routing constraints, and safety behavior.

## 4) Use explicit tool commands only

In `external_llm=true` mode, prefer explicit deterministic commands:

- `check_liveness`
- `get_latest`
- `@record ...`
- `@show records`
- `@reset records`
- `reset context`
- `result = df ...`
- `save`
- `generate_workflow_provenance_card` (markdown report for a workflow id)

## 5) Avoid implicit internal routing

Do **not** rely on free-form natural-language routing inside `prompt_handler`
when `external_llm=true`.

## 6) DataFrame querying flow

Two supported paths:

Internal LLM path:
1. Use `run_df_query` with natural language (internal model required).
2. Agent generates pandas code internally and executes it.

External LLM path (expected in `external_llm=true`):
1. Prompt call (MCP prompt): `build_df_query_prompt`.
2. External LLM reads that prompt and generates explicit pandas code (`result = df ...`).
3. Execute tool call: `execute_generated_df_code(user_code=...)`.

This is the expected external sequence:
- the prompt will instruct you how to generate a dataframe query
- you get the prompt, read it, and generate the query code
- you call the tool that executes the query code

## 7) Recover from context drift

If context is stale/noisy:

1. `reset_context`
2. Re-run explicit commands
3. Continue from deterministic state

## 8) Keep orchestration external

In this mode, treat Flowcept Agent as:
- context + tools backend,
- not the planner.

Use your external LLM orchestrator for reasoning/planning, and Flowcept tools for execution/state.

## 9) Example: External Prompt -> Execute

```python
from flowcept.agents.agent_client import run_prompt, run_tool

# 1) Prompt call
prompt_payload = run_prompt(
    "build_df_query_prompt",
    args={"query": "What are the top 5 slowest activities?"},
    host="127.0.0.1",
    port=8000,
)

# 2) External LLM generates explicit code from prompt
generated_code = (
    "result = df.assign(elapsed_sec=(df['ended_at'] - df['started_at']))"
    ".groupby('activity_id', dropna=False)['elapsed_sec']"
    ".mean().sort_values(ascending=False).head(5)"
    ".reset_index(name='avg_elapsed_sec')"
)

# 3) Execute generated code in agent context
result = run_tool(
    "execute_generated_df_code",
    kwargs={"user_code": generated_code},
    host="127.0.0.1",
    port=8000,
)
```
