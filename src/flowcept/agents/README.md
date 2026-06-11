# Flowcept Agent

This package contains the Flowcept MCP server, client helpers, tools, prompts,
context manager, and optional UI pieces.

For code-assistant behavior, use the repository root `AGENTS.md`. Do not
duplicate agent rules here. Runtime usage docs live in `docs/agent.rst`.

## One Agent, Two Orchestrators

Flowcept Agent has one shared backend and two orchestration paths.

Both paths use the same MCP server, in-memory context, tools, prompts, and
execution functions. The only intended difference is who does routing and LLM
reasoning:

- **Internal LLM mode:** Flowcept builds the configured LLM and orchestrates.
- **External LLM mode:** Codex, Claude, LibreChat, Cursor, or another assistant
  orchestrates and calls Flowcept MCP prompts/tools.

## Shared Backend

- `flowcept_agent.py` starts the MCP server.
- `flowcept_ctx_manager.py` owns the live task/object/workflow context.
- `tools/general_tools.py` exposes `prompt_handler` and shared commands.
- `tools/in_memory_queries/` queries task/object DataFrames.
- `tools/workflow_query_tools.py` queries the active workflow message object.
- `prompts/` builds prompts for internal and external LLM generation.
- `agents_utils.py` builds the configured internal LLM when Flowcept owns
  orchestration.

## Internal LLM Mode

Use this when Flowcept should route free-text messages itself.

```yaml
agent:
  external_llm: false
```

Typical path:

1. A client calls `prompt_handler(message)`.
2. Flowcept builds the configured model with `build_llm_model()`.
3. Flowcept classifies the message with the routing prompt.
4. Flowcept calls the same MCP tools used by the external path.
5. Tool results are returned to the client.

This mode supports natural-language routing through `prompt_handler`, including
task/object DataFrame questions, plots, small talk, records, context reset, and
direct DataFrame code execution.

## External LLM Mode

Use this when an outside assistant should own reasoning and planning.

```yaml
agent:
  external_llm: true
```

Typical path:

1. The outside assistant calls a Flowcept MCP prompt builder.
2. The outside assistant sends that prompt to its own LLM.
3. The outside assistant calls the matching Flowcept execution tool.
4. Flowcept executes against the same live in-memory context.

In this mode, arbitrary free-text messages sent to `prompt_handler` are not
internally routed. This prevents Flowcept from silently becoming the planner
when the outside assistant is supposed to plan.

## Equivalent Tool Paths

| Capability | Internal orchestration | External orchestration |
|---|---|---|
| Task DataFrame question | `prompt_handler("...")` -> `run_df_query(...)` | `build_df_query_prompt(...)` -> external LLM -> `execute_generated_df_code(...)` |
| Object DataFrame question | `prompt_handler("o: ...")` -> `run_df_query(context_kind="objects")` | `build_df_query_prompt(context_kind="objects")` -> external LLM -> `execute_generated_df_code(context_kind="objects")` |
| Workflow metadata question | `prompt_handler("w: ...")` -> `run_workflow_query(...)` | `build_workflow_query_prompt(...)` -> external LLM -> `execute_generated_workflow_query(...)` |
| Direct DataFrame code | `prompt_handler("result = df ...")` | `execute_generated_df_code("result = df ...")` |
| Context reset and records | `prompt_handler("reset context")`, `@record`, `@show records`, `@reset records` | Same tools/commands |
| Provenance reports | Flowcept report tools | Same report tools called explicitly |

## Prefix Shortcuts

These shortcuts are accepted by `prompt_handler` in both modes:

- `t: <question>` queries the task DataFrame.
- `o: <question>` queries the object DataFrame.
- `w: <question>` queries the workflow message object.
- `result = df ...` executes explicit pandas code.
- `save` saves the current DataFrame context.
- `reset context`, `@record`, `@show records`, and `@reset records` manage
  context and guidance.

Important nuance: prefix shortcuts are convenience paths. If a shortcut needs
LLM generation, the current implementation may build Flowcept's configured LLM.
For strict external orchestration, use prompt-builder tools plus execution tools.

## Start The MCP Server

Prefer the CLI:

```bash
flowcept --start-agent
```

Equivalent module form:

```bash
python -m flowcept.agents.flowcept_agent
```

Run from a Python environment where Flowcept is installed.

## Internal Prompt Handler Example

```python
from flowcept.agents.agent_client import run_tool

result = run_tool(
    "prompt_handler",
    kwargs={"message": "What are the top 5 slowest activities?"},
)
```

## External DataFrame Query Example

```python
from flowcept.agents.agent_client import run_prompt, run_tool

prompt = run_prompt(
    "build_df_query_prompt",
    args={"query": "What are the top 5 slowest activities?", "context_kind": "tasks"},
)

# The external assistant sends `prompt` to its own LLM and gets pandas code.
generated_code = (
    "result = df.assign(duration=(df['ended_at'] - df['started_at']))"
    ".groupby('activity_id', dropna=False)['duration']"
    ".mean().sort_values(ascending=False).head(5)"
    ".reset_index(name='avg_duration')"
)

result = run_tool(
    "execute_generated_df_code",
    kwargs={"user_code": generated_code, "context_kind": "tasks"},
)
```

## External Workflow Query Example

```python
from flowcept.agents.agent_client import run_prompt, run_tool

prompt = run_prompt(
    "build_workflow_query_prompt",
    args={"query": "What settings path was used?"},
)

# The external assistant sends `prompt` to its own LLM and gets a JSON spec.
query_spec = {"field_paths": ["conf.settings_path"], "missing": [], "answer_style": "short"}

result = run_tool(
    "execute_generated_workflow_query",
    kwargs={"query_spec": query_spec},
)
```
