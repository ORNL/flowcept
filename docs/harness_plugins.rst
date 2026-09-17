AI Coding Harness Provenance Plugins
====================================

Flowcept can capture what an **AI coding harness** actually did — prompts,
turns, tool calls, subagents — as PROV-AGENT provenance. An agentic coding
session is a workflow: a prompt causes a turn, a turn causes tool calls, a
tool call edits a file. These plugins write that structure into Flowcept's own
record format, so "which prompt produced this bad edit?" becomes a query
instead of a scroll through a transcript.

The shared capture core is ``flowcept.agents.harness``; the per-source plugin
modules live beside it under ``flowcept/agents/``:

.. list-table::
   :header-rows: 1

   * - Source
     - Plugin
   * - Claude Code
     - ``plugins/flowcept`` (Claude Code plugin), or hooks in ``settings.json``
       (adapter: ``flowcept.agents.claude_code``)
   * - Codex CLI, Gemini CLI, Cursor, OpenCode
     - ``flowcept.agents.cli_harness`` — one JSON profile per harness
   * - Anything emitting OpenTelemetry GenAI spans
     - ``flowcept.agents.otel`` span exporter
       (``pip install "flowcept[harness_otel]"``)
   * - Claude Agent SDK
     - ``flowcept.agents.claude_agent_sdk`` ``trace_query``
       (``pip install "flowcept[harness_claude_sdk]"``)
   * - OpenAI Agents SDK
     - ``flowcept.agents.openai_agents`` tracing processor
   * - LangChain / LangGraph
     - ``flowcept.agents.langchain`` callback handler
   * - Your own agent
     - ``flowcept.agents.harness.SessionTracer``, or the
       ``flowcept-harness-mcp`` server's ``record_event`` tool

The capture path is deliberately **stdlib-only**: a harness hook is a fresh
process on the interactive critical path, and importing heavy dependencies
costs far more than the capture itself. Flowcept's heavier dependencies are
only loaded to *read* what was captured.

Quick start: Claude Code
------------------------

Install the Claude Code plugin from this repository:

.. code-block:: text

   /plugin marketplace add <path to the flowcept repo>
   /plugin install flowcept

Then work normally. When you want to see what was recorded:

.. code-block:: bash

   flowcept-harness sessions        # every captured session, newest first
   flowcept-harness show            # the most recent one, turn by turn
   flowcept-harness report          # a Flowcept workflow card

``flowcept-harness install`` prints the equivalent ``settings.json`` if you
would rather wire the hooks yourself than use the plugin.

Quick start: another CLI harness
--------------------------------

Point the harness's hook at the generic profile-driven adapter:

.. code-block:: bash

   flowcept-harness hook --harness codex --profile codex

Profiles live in ``src/flowcept/agents/cli_harness/profiles/`` (``codex``,
``gemini``, ``cursor``, ``opencode``) and are plain JSON: a map from the
harness's event names to normalized ones, and a map from its payload fields
to Flowcept's. Adding a harness means adding a file, not writing code.
``--profile`` also accepts a filesystem path, so a profile can live outside
the package while you iterate on it.

Quick start: Claude Agent SDK
-----------------------------

``trace_query`` is a drop-in for ``claude_agent_sdk.query``:

.. code-block:: python

   from flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin import trace_query

   async for message in trace_query(prompt="fix the failing test"):
       ...

Quick start: OpenTelemetry GenAI spans
--------------------------------------

In-process, for anything already instrumented with OpenTelemetry:

.. code-block:: python

   from opentelemetry.sdk.trace import TracerProvider
   from opentelemetry.sdk.trace.export import SimpleSpanProcessor
   from flowcept.agents.otel.otel_plugin import FlowceptSpanExporter

   provider = TracerProvider()
   provider.add_span_processor(SimpleSpanProcessor(FlowceptSpanExporter()))

Or after the fact, from spans a collector already wrote:

.. code-block:: python

   from flowcept.agents.otel.otel_plugin import ingest_file

   ingest_file("spans.jsonl")

Spans are read through the OTel GenAI semantic conventions:
``gen_ai.operation.name`` separates a model call from a tool call, and
``gen_ai.conversation.id`` groups spans into a session. Spans that are not
GenAI spans are ignored — an HTTP client span is not provenance.

Quick start: in-process capture
-------------------------------

.. code-block:: python

   # OpenAI Agents SDK — register once, nothing else changes
   from flowcept.agents.openai_agents.openai_agents_plugin import install
   install()

   # LangChain / LangGraph — pass the handler as a callback
   from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler
   graph.invoke(state, config={"callbacks": [FlowceptCallbackHandler(session_id="thread-42")]})

Each wrapper is duck-typed against its SDK — nothing imports the SDK it
wraps, so installing one does not drag in the others.

For an agent that is none of the above, drive the session yourself:

.. code-block:: python

   from flowcept.agents.harness import SessionTracer

   with SessionTracer("my_agent", model="claude-opus-5") as tracer:
       tracer.prompt("summarize the repo")
       with tracer.tool("read_file", {"path": "README.md"}) as call:
           call.result(read("README.md"))
       tracer.turn_end("done", usage={"input_tokens": 900})

What gets recorded
------------------

.. code-block:: text

   session                    workflow   (subtype: agent_session)
     turn                     task       (subtype: ai_model_invocation, granularity=turn)
       model call             task       (subtype: ai_model_invocation, granularity=call)
       tool call              task       (subtype: agent_tool)
       subagent               workflow   (subtype: subagent_session) + task
     compaction, notice       task       (subtype: harness_event)

The edges are the point. A tool call's ``parent_task_id`` is its turn; a
subagent's tools live in the subagent's own workflow rather than interleaved
with the parent's; a turn lists the tools it caused. That is the
``wasInformedBy`` chain PROV-AGENT is built around, and it is what lets you
walk from a bad edit back to the prompt that caused it.

Model invocations are recorded at whatever granularity the source can see. A
hook cannot observe individual API calls, so hook-based capture records one
invocation per turn; SDK and OTel capture record both. ``granularity`` in
``custom_metadata`` says which you are looking at.

The buffer / flush model
------------------------

Records are appended as JSONL, one file per session, under
``~/.flowcept/harness/buffers/``. The format is Flowcept's native record
format, so the buffer is directly consumable:

.. code-block:: bash

   flowcept --generate-report --input-path ~/.flowcept/harness/buffers/<id>.jsonl

To push into a live Flowcept backend instead of (or as well as) the file:

.. code-block:: bash

   export FLOWCEPT_HARNESS_ONLINE=1     # publish as you go
   flowcept-harness flush --all         # or publish buffers after the fact

Offline is the default because a hook must never block on a message queue
that may not be running.

The ``flowcept-harness`` CLI
----------------------------

.. code-block:: text

   flowcept-harness sessions     list captured sessions, newest first
   flowcept-harness show         show one session's activity, turn by turn
   flowcept-harness status       configuration and capture health
   flowcept-harness report       generate a Flowcept report from a buffer
   flowcept-harness analyze      analyze one session (failures, latency, links)
   flowcept-harness flush        publish buffered records to a Flowcept backend
   flowcept-harness repair       close sessions a crashed harness left open
   flowcept-harness install      print the settings that enable capture
   flowcept-harness hook         record a payload from stdin (what hooks call)

Useful options:

- ``sessions -n/--limit N`` and ``-v/--verbose``
- ``show [buffer ...]`` — defaults to the most recent session
- ``status --check-backend`` — also probe the Flowcept backend
- ``flush --input <buffer ...> | --all``, plus ``--remove`` (delete buffers
  after a successful flush) and ``--dry-run``
- ``report --input <buffer ...> --type workflow_card --format markdown
  -o/--output <file>``
- ``--home <dir>`` (global) — override the capture home directory

Provenance analysis
-------------------

Captured sessions can be analyzed, not just replayed. The analysis logic is
``flowcept.agents.prov_analysis`` — pure functions over provenance records
(``src/flowcept/agents/prov_analysis/README.md``) — exposed on three
harness-side surfaces:

**MCP analysis tools.** The ``flowcept-harness-mcp`` server exposes four
analysis tools alongside its capture and inspection tools; each takes an
optional ``session`` id prefix and defaults to the most recent session:

- ``analyze_session`` — execution summary (counts, statuses, durations, token
  usage) plus per-agent behavior (turns, tool calls, subagent fan-out).
- ``analyze_errors`` — failure clustering: which activities fail, how often,
  with stderr/message excerpts.
- ``find_slowest`` — the slowest tasks, longest elapsed first, with activity,
  status, and parent-chain depth (``limit`` defaults to 10).
- ``cross_links`` — cross-framework provenance edges built from
  ``source_agent_id`` pointers (e.g. a LangGraph run launched from a coding
  session), plus the count of unlinked tasks. The harness side of the edge is
  written by giving capture a framework-emitted task/agent id: the
  ``flowcept_source_agent_id`` hook-payload key, the
  ``FLOWCEPT_HARNESS_SOURCE_AGENT_ID`` environment variable (payload key
  wins), or ``SessionTracer(..., source_agent_id=...)``.

**CLI.** The same analyses from the terminal:

.. code-block:: bash

   flowcept-harness analyze <session>              # summary + agent behavior
   flowcept-harness analyze <session> --errors     # failure clustering
   flowcept-harness analyze <session> --slowest 5  # latency ranking
   flowcept-harness analyze <session> --links      # cross-framework links
   flowcept-harness analyze --compare <a> <b>      # per-activity deltas of two sessions

``<session>`` is a workflow id or prefix and defaults to the most recent
session. ``--compare`` takes two ids/prefixes instead of the positional
session and prints per-activity count, average-duration, and error-rate
deltas.

**Claude Code plugin.** ``plugins/flowcept`` wires the MCP server in through
its ``.mcp.json``, which declares a ``flowcept-provenance`` stdio server
launched by ``scripts/mcp-server.sh`` — installing the plugin gives Claude
Code the analysis tools with no extra setup. The plugin also ships two
analysis-oriented skills: ``prov-analysis`` (turn captured provenance into
answers: failures, latency, cost, run comparison, cross-framework linkage)
and ``write-flowcept-plugin`` (author a capture plugin for a new harness).
Setting ``FLOWCEPT_HARNESS_AUTOREPORT=1`` additionally enables an opt-in
SessionEnd hook that writes a workflow card per session to
``$FLOWCEPT_HARNESS_HOME/reports/``; it is off by default and exits silently
when unset.

The Flowcept agent MCP server and web chat expose the same analyses over
in-memory and DB records — see :doc:`agent`. A runnable, fully offline
example is ``examples/agents/prov_analysis/prov_analysis_example.py``.

Configuration
-------------

Every knob is an environment variable, so it can be set from a harness
settings file, a plugin's ``userConfig``, or a shell profile. The most
important ones:

.. list-table::
   :header-rows: 1

   * - Variable
     - Default
     - Meaning
   * - ``FLOWCEPT_HARNESS_ENABLED``
     - ``1``
     - Master switch.
   * - ``FLOWCEPT_HARNESS_HOME``
     - ``~/.flowcept/harness``
     - State and buffers.
   * - ``FLOWCEPT_HARNESS_CONTENT``
     - ``summary``
     - File bodies: ``full``, ``summary``, ``none``.
   * - ``FLOWCEPT_HARNESS_REDACT``
     - ``1``
     - Redact credential-shaped keys and literals.
   * - ``FLOWCEPT_HARNESS_CAPTURE_PROMPTS``
     - ``1``
     - Off stores prompt digests only.
   * - ``FLOWCEPT_HARNESS_ONLINE``
     - ``0``
     - Publish to the Flowcept MQ as you go.
   * - ``FLOWCEPT_HARNESS_TIMEOUT_MS``
     - ``2000``
     - Hard ceiling on hook wall time.

The full configuration table (campaign scoping, string truncation, tool-result
capture, debug logging), the privacy posture, and the MCP server
(``flowcept-harness-mcp``) are documented in the package README:
`src/flowcept/agents/harness/README.md
<https://github.com/ORNL/flowcept/blob/main/src/flowcept/agents/harness/README.md>`_.

See also
--------

- ``examples/agents/harness/harness_example.py`` — a ``SessionTracer``
  example.
- :doc:`agent_plugins` — provenance plugins for agentic frameworks
  (Academy, AutoGen, CrewAI, LangChain, LangGraph, OpenAI Agents SDK).
- :doc:`schemas` — the PROV-AGENT data model in Flowcept.
