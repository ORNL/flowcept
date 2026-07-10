Flowcept Agent
==============

Flowcept exposes provenance data to LLM-based agents through two complementary surfaces:

**1. Web Chat Agent (browser-embedded)**
   An interactive chat panel in the Flowcept Web UI (``flowcept --start --ui``) that answers
   natural-language questions about provenance data stored in MongoDB. It queries the
   **persisted provenance store** and is always scoped to the page the user is viewing
   (a specific workflow or campaign). It also supports **streaming-data context**: when a
   workflow is actively running, newly-persisted records are available in near real time
   through the same interface. Capabilities:

   - Query tasks, workflows, campaigns, and agents with natural-language questions.
   - Generate and render charts directly in the chat (e.g., "plot task durations per activity").
   - **Highlight provenance lineage** in the Dataflow graph: ask the agent to identify an
     entity of interest and it will highlight the full ancestor/descendant chain of that
     entity in the Dataflow tab — purely from generic provenance edges (``used`` /
     ``generated``), with no domain-specific logic.
   - Queries are automatically scoped to the current workflow or campaign context.
   - Requires ``agent`` + ``web_server.chat.enabled: true`` in settings (see :doc:`web_ui`).

**2. MCP Agent (external LLM / CLI)**
   A standalone MCP server (``flowcept --start --agent``) that external assistants such as
   Claude Code, Codex, Cursor, or LibreChat connect to. It consumes messages from the
   **live MQ stream** (Redis, Kafka, or Mofka) so it can respond to queries while the
   workflow is still executing. It also supports offline JSONL buffer files.

The two surfaces share the same underlying provenance tool core
(``src/flowcept/agents/data_query_tools/db_query_tools.py``) so queries stay consistent across both.

The MCP agent exposes explicit tools only. The outside assistant, such as Codex,
Claude, LibreChat, Cursor, or another MCP client, owns routing and reasoning,
while Flowcept provides the MCP prompts, tools, and in-memory context.

Configuring LLM orchestration
-----------------------------

.. code-block:: yaml

   agent:
     external_llm: true

When ``agent.external_llm`` is enabled, use explicit commands, prompt-builder
calls, and execution-tool calls from the outside assistant.

Shared commands and prefixes
----------------------------

These commands are available in both modes:

- ``t: <question>`` queries task records.
- ``o: <question>`` queries object records.
- ``w: <question>`` queries the active workflow message object.
- ``result = df ...`` executes explicit pandas code against the active DataFrame.
- ``save`` saves the current DataFrame context.
- ``reset context`` clears the active context.
- ``@record ...``, ``@show records``, and ``@reset records`` manage guidance records.

Online-first design
-------------------
Like Flowcept as a whole, the agent is designed to run **while a workflow is still executing**. In online mode,
it consumes messages from the MQ (typically Redis) so it can respond to queries in near real time. This is the
recommended setup for interactive RAG/MCP analysis during live runs.

Web Chat: streaming vs. persisted queries
------------------------------------------

The web chat agent queries MongoDB (the persisted provenance store). When a workflow is
actively running, the ``DocumentInserter`` consumer continuously flushes MQ messages into
MongoDB, so the chat agent sees near-real-time data without connecting directly to the MQ.

For true in-flight, sub-second streaming queries (before the MQ buffer flushes), use the
MCP agent path, which subscribes to the MQ directly.

Lineage highlighting
~~~~~~~~~~~~~~~~~~~~

Ask the web chat agent to highlight the provenance lineage of any task or group of tasks:

.. code-block:: text

   "highlight the lineage of the slowest task"
   "show me which tasks produced outputs that were later used by failed tasks"
   "highlight the lineage of tasks where status is FINISHED and generated.accuracy exists"

The agent resolves the matching task(s) via a Mongo-style filter, then the Dataflow graph
tab dims all unrelated nodes and edges, tracing only the ancestor/descendant chain.
Click any node or empty space to reset the highlight manually.

Explicit MCP tool example
-------------------------

.. code-block:: python

   from flowcept.agents.mcp.mcp_client import run_tool

   result = run_tool(
       "run_workflow_query",
       kwargs={"query": "What is the workflow name?"},
   )

External prompt plus execution example
--------------------------------------

.. code-block:: python

   from flowcept.agents.mcp.mcp_client import run_prompt, run_tool

   prompt = run_prompt(
       "build_df_query_prompt",
       args={"query": "What are the top 5 slowest activities?", "context_kind": "tasks"},
   )

   # Send `prompt` to the external LLM. It should return pandas code assigned to `result`.
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

External workflow-message query example
---------------------------------------

.. code-block:: python

   from flowcept.agents.mcp.mcp_client import run_prompt, run_tool

   prompt = run_prompt(
       "build_workflow_query_prompt",
       args={"query": "What settings path was used?"},
   )

   # Send `prompt` to the external LLM. It should return a JSON query spec.
   query_spec = {"field_paths": ["conf.settings_path"], "missing": [], "answer_style": "short"}

   result = run_tool(
       "execute_generated_workflow_query",
       kwargs={"query_spec": query_spec},
   )

Offline (file-based) queries
----------------------------
For simple tests or disconnected environments, the agent can also be initialized from a **JSONL buffer file**.
In this mode, Flowcept writes messages to disk (``dump_buffer``), and the agent loads the file once at startup
before serving queries.

This is a minimal offline example:

.. code-block:: python

   import json
   from flowcept import Flowcept, flowcept_task
   from flowcept.agents.mcp.mcp_client import run_tool
   from flowcept.agents.mcp.mcp_server import FlowceptMCPServer

   @flowcept_task
   def sum_one(x):
       return x + 1

   # Run a small workflow and dump the buffer to disk
   with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False) as f:
       sum_one(1)
       f.dump_buffer("flowcept_buffer.jsonl")

   # Start the agent from the buffer file and query it
   agent = FlowceptMCPServer(buffer_path="flowcept_buffer.jsonl")
   # Or load a list of messages directly
   # agent = FlowceptMCPServer(buffer_messages=msgs)
   agent.start()
   resp = run_tool("run_df_query", kwargs={"query": "how many tasks?"})[0]
   print(json.loads(resp))
   agent.stop()
