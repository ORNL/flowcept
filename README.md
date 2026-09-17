<p align="center">
  <picture>
    <source srcset="./docs/img/flowcept-logo-dark.png" media="(prefers-color-scheme: dark)" />
    <source srcset="./docs/img/flowcept-logo.png" media="(prefers-color-scheme: light)" />
    <img src="./docs/img/flowcept-logo.png" alt="Flowcept Logo" width="200"/>
  </picture>
</p>

<h3 align="center">Runtime provenance for distributed scientific and AI workflows</h3>

<p align="center">
Capture, stream, query, visualize, and reason over workflow lineage across ML, agentic, edge, cloud, and HPC systems.
</p>

<p align="center">
  <a href="https://flowcept.org">Website</a> ·
  <a href="https://flowcept.readthedocs.io/">Documentation</a> ·
  <a href="./examples">Examples</a> ·
  <a href="./notebooks">Notebooks</a> ·
  <a href="https://flowcept.readthedocs.io/en/latest/publications.html">Publications</a>
</p>


<p align="center">

  <a href="https://flowcept.readthedocs.io/">
    <img src="https://img.shields.io/badge/docs-readthedocs.io-green.svg" alt="Documentation">
  </a>

  <a href="https://pypi.org/project/flowcept">
    <img src="https://badge.fury.io/py/flowcept.svg" alt="PyPI">
  </a>

  <a href="https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml">
    <img src="https://github.com/ORNL/flowcept/actions/workflows/run-tests.yml/badge.svg" alt="Tests">
  </a>

  <a href="https://github.com/ORNL/flowcept/actions/workflows/checks.yml">
    <img src="https://github.com/ORNL/flowcept/actions/workflows/checks.yml/badge.svg" alt="Checks">
  </a>

  <a href="LICENSE">
    <img src="https://img.shields.io/github/license/ORNL/flowcept" alt="License: MIT">
  </a>

</p>



## What Is Flowcept?

Flowcept is a lightweight runtime provenance data management and data observability system for AI, scientific, and agentic workflows.
It records what ran, what data were used and generated, where it ran, how long it took,
which resources it consumed, and how workflow artifacts relate to each other, with rich context and detailed metadata.

It is designed for workflows that are distributed, heterogeneous, and hard to inspect after the fact:
ML training, agentic workflows, HPC jobs, edge-to-cloud-to-HPC pipelines, Workflow Management System tasks, and multi-workflow campaigns.

Flowcept records can start as simple JSONL files for small local demos, move to LMDB for
pure file-based runs, and scale to MongoDB for cloud deployments, production-style querying, dashboards, and UI use.
For distributed runs, provenance records can also stream through a message queue while the
workflow is still executing. The Flowcept Agent adds LLM-based interaction on top of captured
provenance, so users can ask questions, inspect lineage, and drive visual exploration naturally, both to the in-motion data in the MQ systems or the data persisted in the database. 

## See It In Action

The Flowcept UI turns captured provenance into browsable workflow structure, data lineage,
dashboards, workflow cards, and natural-language provenance exploration.

<img src="./docs/img/FlowceptUI.gif" alt="Flowcept UI" style="max-width: 100%; height: auto;">

## Why Flowcept?

- **Distributed by design**: MQ-based provenance streaming with [Redis](https://redis.io) (default), [RabbitMQ](https://www.rabbitmq.com), [Kafka](https://kafka.apache.org), and [Mofka](https://mofka.readthedocs.io), plus database-backed storage for online querying.
- **Low-overhead HPC capture**: buffer and stream provenance with low interference in large-scale jobs.
- **Plugin-friendly capture**: instrument native code or use adapters, including PyTorch, Dask, MLflow, TensorBoard, and more.
- **AI/ML-ready semantics**: preserve workflow, task, parameter, metric, model, tensor, artifact, telemetry, and resource-usage context.
- **Agentic workflow lineage**: capture agent/tool execution, LLM usage, prompts, responses, and runtime provenance.
- **Flowcept Agent**: chat naturally with captured provenance, inspect workflow data, generate workflow cards, and drive interactive visualizations.
- **Standards-aware provenance**: Flowcept follows the [W3C PROV](https://www.w3.org/TR/prov-overview/) model and extends it for workflow, ML, and agentic execution contexts.

## Quickstart (get it up in 1 minute): Capture Provenance Offline

This minimal example needs no database, broker, or external service.

```bash
pip install flowcept
```

Create `quickstart.py`:

```python
from flowcept import Flowcept, flowcept_task
from flowcept.instrumentation.flowcept_decorator import flowcept


@flowcept_task(output_names="y")
def add_one(x):
    return x + 1


@flowcept_task(output_names="z")
def double(y):
    return y * 2


@flowcept
def main():
    y = add_one(3)
    z = double(y)
    print("result:", z)


if __name__ == "__main__":
    main()
    # print(Flowcept.read_buffer_file())  # inspect raw JSONL records if needed
    Flowcept.generate_report(print_markdown=True)
```

Run it:

```bash
python quickstart.py
```

Flowcept captures task inputs, outputs, timing, workflow structure, and writes a local JSONL buffer.
The final line reads the default buffer file and prints a workflow card.

For the maintained tutorial, read the [Quick Start](https://flowcept.readthedocs.io/en/latest/quick_start.html).

## Use The Web UI

For interactive and live provenance exploration, run Flowcept with MongoDB and the webservice.
The UI shows captured workflows, so run one or more workflows after the service is up to populate the database.

```bash
pip install "flowcept[webservice,mongo]"
make services-mongo
flowcept --init-settings --full -y
flowcept --config-profile full-online -y
flowcept --start --ui
```

Open `http://localhost:5173`.

In another terminal, run a workflow with the same online settings, for example:

```bash
python examples/start_here.py
```

The UI provides:

- **Workflow and campaign browser** for runs, tasks, artifacts, and agents.
- **Dataflow graph** for W3C PROV-style task/data lineage.
- **Task and data inspectors** for metadata, inputs, outputs, timing, and artifact details.
- **Dashboards** for runtime summaries and workflow metrics.
- **Workflow cards** downloadable as Markdown or PDF.
- **Chat agent** for natural-language questions and interactive provenance visualization.

See the [Web UI docs](https://flowcept.readthedocs.io/en/latest/web_ui.html) and [ui/README.md](ui/README.md).

## Flowcept Agent

The Flowcept Agent lets users ask natural language questions over captured provenance instead of hand-writing queries.
It supports two complementary modes:

- **Web chat**: built into the Flowcept UI. The chat webservice route calls Flowcept's LangChain tool orchestrator and keeps answers scoped to the workflow or campaign being viewed.
- **MCP server**: exposes the same provenance tool surface to external assistants such as Codex, Claude Code, or other MCP clients.

The tool surface covers two analysis paths:

- **Streaming provenance tools** query records directly from the runtime stream. These are best for monitoring and runtime analysis while a workflow is still running.
- **Persisted provenance tools** query MongoDB or LMDB. These are best for postmortem analysis, dashboards, workflow cards, and live analysis with a small flush delay.

The Flowcept Agent itself also uses these tools through its LangChain orchestration layer.

Example questions:

- “Which activity took the longest?”
- “Show the lineage of the selected model.”
- “Which input files were larger than 100 MB?”
- “Generate a workflow card for this campaign.”
- “Highlight all tasks related to the best model.”

See the [Flowcept Agent docs](https://flowcept.readthedocs.io/en/latest/agent.html) and [src/flowcept/agents/README.md](src/flowcept/agents/README.md).

## Capture Options

Flowcept supports several capture styles. Use the least invasive one that answers your provenance questions.

| Need | Use |
|---|---|
| Minimal function-level capture | `@flowcept_task` |
| Whole workflow context | `with Flowcept():` or `@flowcept` |
| Custom metadata and manual events | `FlowceptTask` |
| Loop capture | `FlowceptLoop` |
| ML model and tensor semantics | PyTorch instrumentation |
| Tool/framework observability | Dask, MLflow, TensorBoard, MCP, and other adapters |
| Distributed runtime stream | [Redis](https://redis.io), [RabbitMQ](https://www.rabbitmq.com), [Kafka](https://kafka.apache.org), or [Mofka](https://mofka.readthedocs.io) message queues |
| Queryable persistent store | MongoDB or LMDB |

Read [Provenance Capture Methods](https://flowcept.readthedocs.io/en/latest/prov_capture.html) for examples.

## Agentic Provenance Plugins

Flowcept ships with zero-code-change provenance plugins for four popular agentic frameworks: **Academy**, **LangGraph**, **CrewAI**, and **AutoGen**. Each plugin automatically captures:

- **Intra-agent provenance** — individual action/task executions with inputs, outputs, timing, and status
- **Inter-agent provenance** — parent/child relationships between agents and the tasks they spawn
- **LLM call provenance** — every OpenAI or Anthropic API call linked back to the agent action that triggered it (model, prompt, tokens, latency)

### Enabling plugins via `settings.yaml`

Add a `plugins:` block to your `~/.flowcept/settings.yaml`. Only the frameworks you want to track need to be listed:

```yaml
plugins:
  academy:
    enabled: true
    kind: academy
    workflow_name: "my-academy-workflow"
    performance_tracking: true
  langgraph:
    enabled: true
    kind: langgraph
    workflow_name: "my-langgraph-workflow"
    performance_tracking: true
  crewai:
    enabled: true
    kind: crewai
    workflow_name: "my-crewai-workflow"
    performance_tracking: true
  autogen:
    enabled: true
    kind: autogen
    workflow_name: "my-autogen-workflow"
    performance_tracking: true
```

Then wrap your code with `Flowcept()` — all enabled plugins start and stop automatically:

```python
from flowcept import Flowcept

with Flowcept():
    # your Academy / LangGraph / CrewAI / AutoGen code here
    ...
```

### Helper utilities

Each plugin exposes drop-in wrappers to record LLM calls regardless of which framework is active:

| Function / Class | Purpose |
|---|---|
| `openai_chat(prompt, model, ...)` | Call OpenAI and automatically record the call with provenance linkage |
| `anthropic_chat(prompt, model, ...)` | Same for Anthropic Claude models |
| `FlowceptAnthropicClient(client)` | Wrap an existing `anthropic.Anthropic` client to intercept all `messages.create` / `stream` calls |
| `run_team(team, task, ...)` | *(AutoGen only)* Run an autogen team and capture full provenance without an explicit plugin handle |

All four plugins export `openai_chat` and `anthropic_chat` from their respective modules (e.g. `from flowcept.agents.academy.academy_plugin import openai_chat`).

### What gets captured

| Captured field | Academy | LangGraph | CrewAI | AutoGen |
|---|:---:|:---:|:---:|:---:|
| Agent action / node executions | ✓ | ✓ | ✓ | ✓ |
| Inputs and outputs per action | ✓ | ✓ | ✓ | ✓ |
| Timing (start / end / latency) | ✓ | ✓ | ✓ | ✓ |
| Parent–child task linkage | ✓ | ✓ | ✓ | ✓ |
| LLM calls (OpenAI) | ✓ | ✓ | ✓ | ✓ |
| LLM calls (Anthropic) | ✓ | ✓ | ✓ | ✓ |
| Token usage | ✓ | ✓ | ✓ | ✓ |
| Agent ID on LLM calls | ✓ | ✓ | ✓ | ✓ |
| Automatic agent wrapping | ✓ | ✓ | — | ✓ |

### Provenance record types per plugin

Each plugin emits typed `TaskObject` records tagged with a `subtype` field, forming a nested provenance hierarchy:

| Plugin | Record subtypes and hierarchy |
|---|---|
| **Academy** | Campaign `WorkflowObject` → agent `WorkflowObject` → `academy_action` / `academy_loop` / `academy_lifecycle` (siblings) → `llm_call` (under action or loop) |
| **LangGraph** | `WorkflowObject` → `langgraph_graph` → `langgraph_node` → `llm_call` / `tool_call` |
| **CrewAI** | `WorkflowObject` → `crewai_crew` (no children via `parent_task_id`) · `crewai_task` → `crewai_agent` → `llm_call` / `tool_call` |
| **AutoGen** | `WorkflowObject` → `autogen_run` → `autogen_message` → `llm_call` |

All records carry `campaign_id`, `workflow_id`, `task_id`, `started_at`, `ended_at`, and `status`. `used` (inputs) and `generated` (outputs) are present on records that represent computation (`academy_action`, node/graph records, LLM and tool calls); `parent_task_id` links child records to their enclosing parent.

### Cross-plugin composition

All four plugins can run under a **shared `campaign_id`** using the `from_academy_plugin()` factory. AutoGen and CrewAI share the Academy plugin's in-memory buffer directly; LangGraph creates its own interceptor but inherits the same `campaign_id`:

```python
from flowcept.agents.academy.academy_plugin import FlowceptAcademyPlugin
from flowcept.agents.langgraph.langgraph_plugin import FlowceptLangGraphPlugin
from flowcept.agents.autogen.autogen_plugin import FlowceptAutoGenPlugin
from flowcept.agents.crewai.crewai_plugin import FlowceptCrewAIPlugin

ap = FlowceptAcademyPlugin(config={"workflow_name": "my-run"})
ap.start()
lg = FlowceptLangGraphPlugin.from_academy_plugin(ap)   # own interceptor, shared campaign_id
ag = FlowceptAutoGenPlugin.from_academy_plugin(ap)     # shared buffer
cr = FlowceptCrewAIPlugin.from_academy_plugin(ap)      # shared buffer

# ... run workloads ...

lg.stop()   # flush LangGraph's interceptor
ap.stop()   # flush Academy / AutoGen / CrewAI shared buffer
```

Every record across all four plugins carries the same `campaign_id`, so a single query retrieves the full cross-framework provenance trace.

### Cross-framework provenance linking

When an Academy `@action` launches a LangGraph graph or an AutoGen team, the plugins can record an explicit parent–child edge across framework boundaries.

**Academy (source side)** — two `contextvars.ContextVar` values are set automatically during execution:

- `_current_academy_agent_id` — the Academy agent identifier, set once per agent at startup
- `_current_action_task_id` — the Flowcept `task_id` of the currently-executing `@action` or `@loop`

Read the latter inside an action to get the enclosing task's identifier:

```python
from flowcept.agents.academy.academy_plugin import _current_action_task_id
action_task_id = _current_action_task_id.get()
```

**LangGraph (target side)** — pass the action's `task_id` as `_source_agent_id` in the initial graph state:

```python
result = await graph.ainvoke(
    {"_source_agent_id": action_task_id, ...},
    config={"callbacks": [lg.callback_handler]},
)
```

The LangGraph plugin stores it as `source_agent_id` in `custom_metadata` of both `langgraph_graph` and `langgraph_node` records.

**AutoGen (target side)** — pass it as `source_agent_id` to `run_team()`:

```python
result = await ag.run_team(team, task, source_agent_id=action_task_id)
```

The AutoGen plugin stores it in `custom_metadata` of the `autogen_run` record.

**AI coding harness (target side)** — the harness capture (`flowcept.agents.harness`) links the other way too: give it a framework-emitted task or agent id and every turn, tool, and LLM-call task it records carries it as a top-level `source_agent_id`. Set it with the `flowcept_source_agent_id` hook-payload key, the `FLOWCEPT_HARNESS_SOURCE_AGENT_ID` environment variable (the payload key wins), or `SessionTracer(..., source_agent_id=...)`:

```python
from flowcept.agents.harness import SessionTracer

with SessionTracer("my_agent", source_agent_id=action_task_id) as tracer:
    ...
```

In all cases, `campaign_id` and `workflow_id` alone are sufficient for coarse-grained cross-framework queries without explicit identifier threading.

### Examples

Runnable examples for each framework are in [`examples/agents/`](examples/agents/):

- [`examples/agents/academy/academy_example.py`](examples/agents/academy/academy_example.py)
- [`examples/agents/langgraph/langgraph_example.py`](examples/agents/langgraph/langgraph_example.py)
- [`examples/agents/crewai/crewai_example.py`](examples/agents/crewai/crewai_example.py)
- [`examples/agents/autogen/autogen_example.py`](examples/agents/autogen/autogen_example.py)
- [`examples/agents/combined_agentic_systems/combined_example.py`](examples/agents/combined_agentic_systems/combined_example.py) — all four frameworks running concurrently
- [`examples/agents/langchain/langchain_example.py`](examples/agents/langchain/langchain_example.py) — LangChain callback handler capture with a fake chat model (runs offline)
- [`examples/agents/openai_agents/openai_agents_example.py`](examples/agents/openai_agents/openai_agents_example.py) — OpenAI Agents SDK tracing processor; runs a real agent with `OPENAI_API_KEY`, or synthetic SDK spans offline
- [`examples/agents/otel/otel_example.py`](examples/agents/otel/otel_example.py) — OpenTelemetry GenAI span exporter fed by synthetic spans (runs offline)
- [`examples/agents/cli_harness/cli_harness_example.py`](examples/agents/cli_harness/cli_harness_example.py) — profile-driven CLI-harness adapter, replaying Codex-style hook events (runs offline)
- [`examples/agents/claude_code/claude_code_example.py`](examples/agents/claude_code/claude_code_example.py) — Claude Code install walkthrough plus a simulated hook-event replay (runs offline)
- [`examples/agents/claude_agent_sdk/claude_agent_sdk_example.py`](examples/agents/claude_agent_sdk/claude_agent_sdk_example.py) — `trace_query` drop-in for `claude_agent_sdk.query` (requires `ANTHROPIC_API_KEY`)
- [`examples/agents/prov_analysis/prov_analysis_example.py`](examples/agents/prov_analysis/prov_analysis_example.py) — agentic provenance analysis: replays two synthetic sessions and runs every `prov_analysis` function over them (runs offline)

## AI Coding Harness Provenance Plugins

Flowcept also captures what an **AI coding harness** actually did — prompts, turns,
tool calls, subagents — as PROV-AGENT provenance. An agentic coding session is a
workflow: a prompt causes a turn, a turn causes tool calls, a tool call edits a
file. These plugins write that structure into Flowcept's own record format, so
"which prompt produced this bad edit?" becomes a query instead of a scroll
through a transcript.

| Source | Plugin |
| --- | --- |
| Claude Code | [`plugins/flowcept`](plugins/flowcept) (Claude Code plugin), or hooks in `settings.json` |
| Codex CLI, Gemini CLI, Cursor, OpenCode | [`flowcept.agents.cli_harness`](src/flowcept/agents/cli_harness/) — one JSON profile per harness |
| Anything emitting OpenTelemetry GenAI spans | [`flowcept.agents.otel`](src/flowcept/agents/otel/) span exporter (`pip install flowcept[harness_otel]`) |
| Claude Agent SDK | [`flowcept.agents.claude_agent_sdk`](src/flowcept/agents/claude_agent_sdk/) `trace_query` (`pip install flowcept[harness_claude_sdk]`) |
| OpenAI Agents SDK | [`flowcept.agents.openai_agents`](src/flowcept/agents/openai_agents/) tracing processor |
| LangChain / LangGraph | [`flowcept.agents.langchain`](src/flowcept/agents/langchain/) callback handler |
| Your own agent | `flowcept.agents.harness.SessionTracer`, or the `flowcept-harness-mcp` server's `record_event` tool |

The capture path is deliberately **stdlib-only**: a harness hook is a fresh process
on the interactive critical path, and importing heavy dependencies costs far more
than the capture itself. Records are appended as JSONL, one file per session, under
`~/.flowcept/harness/buffers/`, in Flowcept's native format.

### Quick start: Claude Code

```
/plugin marketplace add <path to this repo>
/plugin install flowcept
```

Then work normally, and when you want to see what was recorded:

```bash
flowcept-harness sessions        # every captured session, newest first
flowcept-harness show            # the most recent one, turn by turn
flowcept-harness report          # a Flowcept workflow card
```

### Quick start: another CLI harness

Point the harness's hook at the profile-driven adapter:

```bash
flowcept-harness hook --harness codex --profile codex
```

Profiles live in [`src/flowcept/agents/cli_harness/profiles/`](src/flowcept/agents/cli_harness/profiles/)
and are plain JSON — adding a harness means adding a file, not writing code.

### Quick start: in-process capture

```python
# OpenTelemetry GenAI spans
from flowcept.agents.otel.otel_plugin import FlowceptSpanExporter

# OpenAI Agents SDK — register once, nothing else changes
from flowcept.agents.openai_agents.openai_agents_plugin import install
install()

# LangChain / LangGraph
from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler

# Claude Agent SDK — a drop-in for claude_agent_sdk.query
from flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin import trace_query

# Your own agent
from flowcept.agents.harness import SessionTracer
```

See [`examples/agents/harness/harness_example.py`](examples/agents/harness/harness_example.py)
and `flowcept-harness --help` for the full CLI (status, flush to a live Flowcept
backend, repair of crashed sessions). Configuration is via `FLOWCEPT_HARNESS_*`
environment variables, including redaction of credential-shaped values, prompt
digests instead of full prompts, and offline-first buffering. Full documentation,
including the configuration table, privacy posture, and the record model, is in
[`src/flowcept/agents/harness/README.md`](src/flowcept/agents/harness/README.md).

### Provenance analysis

Captured sessions can be analyzed, not just replayed. The analysis logic lives
in [`flowcept.agents.prov_analysis`](src/flowcept/agents/prov_analysis/) —
pure functions over provenance records — and is exposed on every surface:

- **Harness MCP tools** — the `flowcept-harness-mcp` server adds
  `analyze_session` (summary + agent behavior), `analyze_errors` (failure
  clustering with excerpts), `find_slowest` (latency ranking), and
  `cross_links` (edges across framework boundaries).
- **CLI** — `flowcept-harness analyze <session> [--errors | --slowest N | --links]`
  runs the same analyses over a session's buffer.
- **Claude Code plugin** — [`plugins/flowcept`](plugins/flowcept) wires the MCP
  server in via its `.mcp.json` (a stdio server launched by
  `scripts/mcp-server.sh`) and ships two skills: `prov-analysis` (turn captured
  provenance into answers) and `write-flowcept-plugin` (author a capture plugin
  for a new harness). Set `FLOWCEPT_HARNESS_AUTOREPORT=1` to have the plugin
  write a workflow card per session on SessionEnd (opt-in, off by default).
- **Flowcept agent MCP / web chat** — `df_*`/`db_*` analysis tools and
  `compare_executions` over the agent's in-memory context or the DB.

See [`examples/agents/prov_analysis/prov_analysis_example.py`](examples/agents/prov_analysis/prov_analysis_example.py)
and [`src/flowcept/agents/prov_analysis/README.md`](src/flowcept/agents/prov_analysis/README.md).

## Storage And Querying

Flowcept can run fully offline or as an online distributed system.

| Mode | What happens |
|---|---|
| Offline JSONL | Provenance is captured locally and can be loaded later. |
| MQ stream | Runtime records are streamed through [Redis](https://redis.io), [RabbitMQ](https://www.rabbitmq.com), [Kafka](https://kafka.apache.org), or [Mofka](https://mofka.readthedocs.io). |
| MongoDB | Rich online queries, web UI, dashboards, workflow cards, and agent chat. |
| LMDB | Lightweight local persistence without an external database service. |

Query surfaces:

- Python API: `Flowcept.db`
- CLI: `flowcept --query ...`
- REST API: `flowcept --start --webservice`
- Web UI: browser-based exploration and dashboards
- Flowcept Agent: natural-language provenance querying and reasoning

Read [Provenance Querying](https://flowcept.readthedocs.io/en/latest/prov_query.html), [Provenance Storage](https://flowcept.readthedocs.io/en/latest/prov_storage.html), and the [REST API docs](https://flowcept.readthedocs.io/en/latest/rest_api.html).

## Workflow Cards

Flowcept generates workflow cards: structured run summaries for reproducibility, review, and communication.
Cards include workflow metadata, execution status, activity summaries, resource usage, artifacts, and lineage structure.

```python
from flowcept import Flowcept

Flowcept.generate_report(workflow_id="<workflow-id>")
Flowcept.generate_report(campaign_id="<campaign-id>")
Flowcept.generate_report(workflow_id="<workflow-id>", format="pdf")
```

The Markdown workflow cards follow the upstream
[Workflow Provenance Card template](https://github.com/data-cards/workflow-provenance-card).

Read the [Reporting docs](https://flowcept.readthedocs.io/en/latest/reporting.html).

## Installation

Install only what you need.

```bash
pip install flowcept                  # minimal package
pip install "flowcept[mongo]"         # MongoDB support
pip install "flowcept[webservice]"    # REST API and web UI
pip install "flowcept[dask]"          # Dask adapter
pip install "flowcept[mlflow]"        # MLflow adapter
pip install "flowcept[rabbitmq]"      # RabbitMQ MQ
pip install "flowcept[kafka]"         # Kafka MQ
pip install "flowcept[telemetry]"     # CPU/memory telemetry
pip install "flowcept[lmdb]"          # LMDB storage
pip install "flowcept[llm_agent]"     # Flowcept Agent / MCP / chat dependencies
```

`flowcept[all]` exists for development and broad testing, but it is usually better to install targeted extras.

Read [Setup and Installation](https://flowcept.readthedocs.io/en/latest/setup.html).

## Settings

Flowcept is configured through `settings.yaml`, with environment variables taking precedence.

```bash
flowcept --init-settings -y              # minimal settings
flowcept --init-settings --full -y       # full template
flowcept --config-profile full-online -y # online MQ + DB profile
```

Configuration precedence:

1. Environment variables.
2. `FLOWCEPT_SETTINGS_PATH`.
3. `~/.flowcept/settings.yaml`.
4. Built-in defaults.

Read the [CLI Reference](https://flowcept.readthedocs.io/en/latest/cli-reference.html).

## Examples And Notebooks

- [examples](examples): runnable scripts for decorators, Dask, MLflow, TensorBoard, PyTorch, agents, consumers, and object storage.
- [notebooks](notebooks): exploratory examples and tutorials.
- [Default User Guide](https://flowcept.readthedocs.io/en/latest/default_user_guide.html): recommended end-to-end guide.

## For Code Assistants

Code assistants should read [AGENTS.md](AGENTS.md) first.
It is the single source of truth for repository-specific engineering rules.

For Flowcept feature usage, read the maintained RST docs under [docs](docs) instead of inventing behavior from source snippets.

## Cite Flowcept

If you use Flowcept in research, please cite:

```bibtex
@inproceedings{souza2023towards,
  author = {Souza, Renan and Skluzacek, Tyler J and Wilkinson, Sean R and Ziatdinov, Maxim and da Silva, Rafael Ferreira},
  booktitle = {IEEE International Conference on e-Science},
  doi = {10.1109/e-Science58273.2023.10254822},
  link = {https://doi.org/10.1109/e-Science58273.2023.10254822},
  pdf = {https://arxiv.org/pdf/2308.09004.pdf},
  title = {Towards Lightweight Data Integration using Multi-workflow Provenance and Data Observability},
  year = {2023}
}
```

More publications are listed in the [Flowcept publications page](https://flowcept.readthedocs.io/en/latest/publications.html).

## Community And Contributing

Flowcept is research software developed for distributed scientific workflows.
Issues, discussions, examples, adapters, and documentation improvements are welcome.

- [Contributing guide](CONTRIBUTING.md)
- [GitHub issues](https://github.com/ORNL/flowcept/issues/new)
- [GitHub discussions](https://github.com/ORNL/flowcept/discussions/new/choose)
- [Slack channel](https://workflowscommunity.slack.com/archives/C06L5GYJKQS)

## Acknowledgement

This research uses resources of the Oak Ridge Leadership Computing Facility at Oak Ridge National Laboratory,
which is supported by the Office of Science of the U.S. Department of Energy under Contract No. DE-AC05-00OR22725.
