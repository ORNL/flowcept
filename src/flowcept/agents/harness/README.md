# AI coding harness provenance (`flowcept.agents.harness`)

Capture what an AI coding harness actually did — prompts, turns, tool calls,
subagents — as [Flowcept](https://github.com/ORNL/flowcept) provenance.

This package is the shared capture core; the per-harness plugin modules live
beside it under `flowcept/agents/` (`claude_code/`, `cli_harness/`, `otel/`,
`claude_agent_sdk/`, `openai_agents/`, `langchain/`), following the same layout
as the agent-framework plugins (`academy/`, `langgraph/`, `crewai/`,
`autogen/`).

Agentic coding sessions are workflows: a prompt causes a turn, a turn causes
tool calls, a tool call edits a file. That is exactly the structure Flowcept
already stores and queries for scientific workflows, and
[PROV-AGENT](https://arxiv.org/abs/2508.02866) is the W3C PROV extension that
names the pieces. This package writes that structure out of the harnesses you
already use, so "which prompt produced this bad edit?" is a query rather than a
scroll back through a transcript.

Supported sources:

| Source | How |
| --- | --- |
| Claude Code | plugin (hooks), or hooks in `settings.json` |
| Codex CLI, Gemini CLI, Cursor, OpenCode | generic hook adapter + a JSON profile |
| Anything emitting OpenTelemetry GenAI spans | span exporter, or ingest exported spans |
| Claude Agent SDK | `trace_query`, or feed the message stream to a tracer |
| OpenAI Agents SDK | a tracing processor |
| LangChain / LangGraph | a callback handler |
| Your own agent | `SessionTracer`, or the MCP server's `record_event` tool |

## Install

Ships with flowcept itself:

```bash
pip install flowcept                       # capture, query, and report
pip install "flowcept[harness_otel]"       # + the OTel span exporter
pip install "flowcept[harness_claude_sdk]" # + the Claude Agent SDK wrapper
```

The capture path is deliberately stdlib-only — it imports nothing outside
`flowcept.agents.harness` and the standard library. A Claude Code hook is a
fresh process on the interactive critical path, and importing flowcept's heavy
dependencies costs far more than the capture itself; those are only loaded to
*read* what was captured.

## Quick start: Claude Code

```
/plugin marketplace add <path to this repo>
/plugin install flowcept
```

Then work normally. When you want to see what was recorded:

```bash
flowcept-harness sessions        # every captured session, newest first
flowcept-harness show            # the most recent one, turn by turn
flowcept-harness report          # a Flowcept workflow card
```

`flowcept-harness install` prints the equivalent `settings.json` if you would
rather wire the hooks yourself than use the plugin.

## Quick start: another CLI harness

Point the harness's hook at the generic adapter with the matching profile:

```bash
flowcept-harness hook --harness codex --profile codex
```

Profiles live in [`src/flowcept/agents/cli_harness/profiles/`](src/flowcept/agents/cli_harness/profiles/)
and are plain JSON: a map from the harness's event names to normalized ones,
and a map from its payload fields to ours. Adding a harness means adding a file,
not writing code. `--profile` also accepts a path, so a profile can live outside
the package while you iterate on it.

## Quick start: OpenTelemetry

In-process, for anything already instrumented:

```python
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from flowcept.agents.otel.otel_plugin import FlowceptSpanExporter

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(FlowceptSpanExporter()))
```

Or after the fact, from spans a collector already wrote:

```bash
python -c "from flowcept.agents.otel.otel_plugin import ingest_file; ingest_file('spans.jsonl')"
```

Spans are read through the OTel GenAI semantic conventions:
`gen_ai.operation.name` separates a model call from a tool call,
`gen_ai.conversation.id` groups spans into a session. Spans that are not GenAI
spans are ignored — an HTTP client span is not provenance.

## Quick start: the SDKs

```python
# Claude Agent SDK — a drop-in for claude_agent_sdk.query
from flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin import trace_query

async for message in trace_query(prompt="fix the failing test"):
    ...

# OpenAI Agents SDK — register once, nothing else changes
from flowcept.agents.openai_agents.openai_agents_plugin import install

install()

# LangChain / LangGraph — pass the handler as a callback
from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler

graph.invoke(state, config={"callbacks": [FlowceptCallbackHandler(session_id="thread-42")]})
```

Each wrapper is duck-typed against its SDK — nothing imports the SDK it wraps,
so installing one does not drag in the others.

For an agent that is none of the above, drive the session yourself:

```python
from flowcept.agents.harness import SessionTracer

with SessionTracer("my_agent", model="claude-opus-5") as tracer:
    tracer.prompt("summarize the repo")
    with tracer.tool("read_file", {"path": "README.md"}) as call:
        call.result(read("README.md"))
    tracer.turn_end("done", usage={"input_tokens": 900})
```

## What gets recorded

```
session                    workflow   (subtype: agent_session)
  turn                     task       (subtype: ai_model_invocation, granularity=turn)
    model call             task       (subtype: ai_model_invocation, granularity=call)
    tool call              task       (subtype: agent_tool)
    subagent               workflow   (subtype: subagent_session) + task
  compaction, notice       task       (subtype: harness_event)
```

The edges are the point. A tool call's `parent_task_id` is its turn; a
subagent's tools live in the subagent's own workflow rather than interleaved
with the parent's; a turn lists the tools it caused. That is the
`wasInformedBy` chain PROV-AGENT is built around, and it is what lets you walk
from a bad edit back to the prompt that caused it.

Model invocations are recorded at whatever granularity the source can see. A
hook cannot observe individual API calls, so hook-based capture records one
invocation per turn; SDK and OTel capture record both. `granularity` in
`custom_metadata` says which you are looking at.

### Linking to other capture systems

Harness sessions can point back at provenance emitted by the agent-framework
plugins (LangGraph, Academy, AutoGen, ...). Give the harness a
framework-emitted task or agent id and every turn, tool, and LLM-call task it
records carries it as `source_agent_id`:

- **hook payload** — a `flowcept_source_agent_id` key in the payload (set by a
  wrapper or whatever launches the harness) wins for that event;
- **environment** — `FLOWCEPT_HARNESS_SOURCE_AGENT_ID` applies to every event
  of the process it is set for;
- **SessionTracer** — pass `source_agent_id=...` when constructing the tracer.

The reverse direction (a framework record pointing at a harness task) is the
framework plugins' `_source_agent_id` / `source_agent_id` input, and
`flowcept-harness analyze --links` walks both kinds of edge.

## Where it goes

Records are appended as JSONL, one file per session, under
`~/.flowcept/harness/buffers/`. The format is Flowcept's own, so the buffer is
directly consumable:

```bash
flowcept --generate-report --input-path ~/.flowcept/harness/buffers/<id>.jsonl
```

To push into a live Flowcept backend instead of (or as well as) the file:

```bash
export FLOWCEPT_HARNESS_ONLINE=1     # publish as you go
flowcept-harness flush --all         # or publish buffers after the fact
```

Offline is the default because a hook must never block on a message queue that
may not be running.

## Configuration

Every knob is an environment variable, so it can be set from a harness settings
file, a plugin's `userConfig`, or a shell profile.

| Variable | Default | Meaning |
| --- | --- | --- |
| `FLOWCEPT_HARNESS_ENABLED` | `1` | Master switch. |
| `FLOWCEPT_HARNESS_HOME` | `~/.flowcept/harness` | State and buffers. |
| `FLOWCEPT_HARNESS_BUFFER_DIR` | *(under home)* | Buffers elsewhere. |
| `FLOWCEPT_HARNESS_CAMPAIGN_SCOPE` | `project` | `project`, `global`, or `none`. |
| `FLOWCEPT_HARNESS_CAMPAIGN_ID` | *(derived)* | Pin sessions to one campaign. |
| `FLOWCEPT_HARNESS_CONTENT` | `summary` | File bodies: `full`, `summary`, `none`. |
| `FLOWCEPT_HARNESS_MAX_STR` | `4000` | Max characters per captured string. |
| `FLOWCEPT_HARNESS_REDACT` | `1` | Redact credential-shaped keys and literals. |
| `FLOWCEPT_HARNESS_CAPTURE_PROMPTS` | `1` | Off stores prompt digests only. |
| `FLOWCEPT_HARNESS_CAPTURE_TOOL_RESULTS` | `1` | Off stores inputs but not outputs. |
| `FLOWCEPT_HARNESS_SOURCE_AGENT_ID` | *(unset)* | Link tasks to another system's task/agent id. |
| `FLOWCEPT_HARNESS_ONLINE` | `0` | Publish to the Flowcept MQ as you go. |
| `FLOWCEPT_HARNESS_TIMEOUT_MS` | `2000` | Hard ceiling on hook wall time. |
| `FLOWCEPT_HARNESS_DEBUG` | `0` | Log capture failures instead of staying silent. |

### Privacy

Prompts and tool inputs are captured by default, because provenance without
them answers very little. What is *not* captured: values under
credential-shaped keys and literals matching known key formats are replaced
with `«redacted»` at capture time, not at query time, since provenance is
long-lived and often shared. File bodies in `Write`/`Edit` inputs are reduced to
a size, a line count, a hash, and a 200-character preview.

For a stricter posture, `FLOWCEPT_HARNESS_CONTENT=none` drops file bodies
entirely and `FLOWCEPT_HARNESS_CAPTURE_PROMPTS=0` keeps only a digest of each
prompt — enough to tell two prompts apart, not enough to read them.

## The MCP server

Exposes captured provenance to an agent as tools, so a session can ask about
its own history:

```bash
flowcept-harness-mcp
```

Tools: `list_sessions`, `get_session`, `search_tool_calls`, `session_stats`,
`record_event`, `generate_report`. `record_event` also makes the server a
capture path in its own right, for a harness that speaks MCP but has no hooks.

## Never harming the harness

Capture code runs inside an interactive tool, which constrains it more than
correctness alone would:

- **Nothing on stdout.** Claude Code injects hook stdout into the model's
  context on some events; a provenance record must not become a prompt.
- **Always exit 0.** A capture failure is logged, never reported to the user as
  a broken hook.
- **A watchdog.** Past `TIMEOUT_MS` the process hard-exits. Losing one record
  beats stalling the UI.
- **Crash-safe records.** A session's workflow record is written when it opens,
  so an interrupted run is still readable, and rewritten when it closes.
- **Concurrency-safe.** Session state is a locked read-modify-write and
  appends are locked, so parallel subagents cannot interleave a record.

`flowcept-harness repair` closes sessions left open by a harness that died.

## CLI

```
flowcept-harness sessions     list captured sessions
flowcept-harness show         show one session's activity
flowcept-harness analyze      analyze a session (--errors, --slowest, --links, --compare A B)
flowcept-harness status       configuration and capture health
flowcept-harness report       generate a Flowcept report
flowcept-harness flush        publish buffers to a Flowcept backend
flowcept-harness repair       close sessions a crashed harness left open
flowcept-harness install      print the settings that enable capture
flowcept-harness hook         record a payload from stdin (what hooks call)
```

## Development

From the repository root:

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]" "mcp>=1.0.0" "opentelemetry-sdk>=1.20.0"
.venv/bin/python -m pytest tests/harness
```

Tests drive the real thing wherever there is one: the Flowcept interop tests
run against installed flowcept, the MCP tests run a real stdio client
handshake, and the OTel exporter test runs through a real tracer provider. The
SDK wrappers are tested against payload-shaped objects, since duck-typing is
the contract they are written to.

## Layout

```
src/flowcept/agents/
  harness/                 the shared capture core (this package)
    events.py              the harness-independent event every adapter produces
    recorder.py            the state machine that turns events into PROV-AGENT records
    prov.py                record constructors
    ids.py                 deterministic UUIDv5 ids, so separate processes agree
    emit.py                JSONL buffers, locking, and online publishing
    sanitize.py            redaction, truncation, JSON-safety
    state.py               locked per-session state
    tracer.py              SessionTracer, for agents you write yourself
    cli.py                 the command line
    mcp_server.py          provenance as MCP tools
  claude_code/             Claude Code hook adapter
  cli_harness/             profile-driven adapter (+ profiles/: codex, gemini, cursor, opencode)
  otel/                    OTel GenAI span exporter and ingest
  claude_agent_sdk/        trace_query wrapper
  openai_agents/           tracing processor
  langchain/               callback handler
plugins/flowcept/          the Claude Code plugin
tests/harness/             the test suite
examples/agents/harness/   a SessionTracer example
```
