Flowcept Agent
==============

The Flowcept Agent is an MCP-powered interface for querying provenance data while a workflow runs or from a JSONL
buffer file. It exposes tools for task queries, object queries, workflow-message queries, context reset, guidance
records, and report generation.

The agent has one backend and two orchestration paths:

- **Internal LLM mode**: Flowcept builds the configured LLM and routes free-text messages through ``prompt_handler``.
- **External LLM mode**: your outside assistant, such as Codex, Claude, LibreChat, Cursor, or another MCP client,
  owns routing and reasoning, while Flowcept provides the same MCP prompts, tools, and in-memory context.

The modes are intended to expose the same functionality. The difference is only who orchestrates the tools.

Configuring LLM orchestration
-----------------------------

Internal mode:

.. code-block:: yaml

   agent:
     external_llm: false

External mode:

.. code-block:: yaml

   agent:
     external_llm: true

In external mode, arbitrary free-text messages sent to ``prompt_handler`` are not internally routed. Use explicit
commands, prompt-builder calls, and execution-tool calls from the outside assistant.

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

Internal prompt-handler example
-------------------------------

.. code-block:: python

   from flowcept.agents.agent_client import run_tool

   result = run_tool(
       "prompt_handler",
       kwargs={"message": "What are the top 5 slowest activities?"},
   )

External prompt plus execution example
--------------------------------------

.. code-block:: python

   from flowcept.agents.agent_client import run_prompt, run_tool

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

   from flowcept.agents.agent_client import run_prompt, run_tool

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
   from flowcept.agents.flowcept_agent import FlowceptAgent

   @flowcept_task
   def sum_one(x):
       return x + 1

   # Run a small workflow and dump the buffer to disk
   with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False) as f:
       sum_one(1)
       f.dump_buffer("flowcept_buffer.jsonl")

   # Start the agent from the buffer file and query it
   agent = FlowceptAgent(buffer_path="flowcept_buffer.jsonl")
   # Or load a list of messages directly
   # agent = FlowceptAgent(buffer_messages=msgs)
   agent.start()
   resp = agent.query("how many tasks?")
   print(json.loads(resp))
   agent.stop()
