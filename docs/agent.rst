Flowcept Agent
==============

The Flowcept Agent is an MCP-powered LLM interface for querying provenance data. It exposes a small set of tools
(e.g., ``prompt_handler``) that route natural-language questions to in-memory queries over captured task summaries.

Online-first design
------------------
Like Flowcept as a whole, the agent is designed to run **while a workflow is still executing**. In online mode,
it consumes messages from the MQ (typically Redis) so it can respond to queries in near real time. This is the
recommended setup for interactive RAG/MCP analysis during live runs.

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
   agent.start()
   resp = agent.query("how many tasks?")
   print(json.loads(resp))
   agent.stop()

In the future, this page will include a full **online** example (live MQ + Redis) and deployment guidance.
