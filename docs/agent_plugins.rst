Agentic Framework Provenance Plugins
====================================

Flowcept ships zero-code-change provenance plugins for popular agentic
frameworks: **Academy**, **AutoGen**, **CrewAI**, **LangChain**, **LangGraph**,
and the **OpenAI Agents SDK**. Each plugin automatically captures:

- **Intra-agent provenance** — individual action/task executions with inputs,
  outputs, timing, and status.
- **Inter-agent provenance** — parent/child relationships between agents and
  the tasks they spawn.
- **LLM call provenance** — every OpenAI or Anthropic API call linked back to
  the agent action that triggered it (model, prompt, tokens, latency).

The Academy, AutoGen, CrewAI, and LangGraph plugins emit Flowcept
``WorkflowObject`` / ``TaskObject`` records directly and can be auto-started
from ``settings.yaml``. The LangChain callback handler and the OpenAI Agents
SDK tracing processor are in-process capture plugins that share the harness
record model described in :doc:`harness_plugins`.

Enabling plugins via ``settings.yaml``
--------------------------------------

Add a ``plugins:`` block to your ``~/.flowcept/settings.yaml``. Only the
frameworks you want to track need to be listed. Supported ``kind`` values are
``academy``, ``langgraph``, ``crewai``, and ``autogen``:

.. code-block:: yaml

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

Then wrap your code with ``Flowcept()`` — all enabled plugins start and stop
automatically, and every auto-started plugin inherits Flowcept's
``campaign_id``:

.. code-block:: python

   from flowcept import Flowcept

   with Flowcept():
       # your Academy / LangGraph / CrewAI / AutoGen code here
       ...

Running plugin instances are available as ``flowcept_instance.plugins``, a
dict keyed by the plugin's config name.

Helper utilities
----------------

The Academy, AutoGen, CrewAI, and LangGraph plugin modules each export drop-in
wrappers that record LLM calls regardless of which framework is active:

- ``openai_chat(prompt, model, ...)`` — call OpenAI and automatically record
  the call with provenance linkage.
- ``anthropic_chat(prompt, model, ...)`` — the same for Anthropic Claude
  models.
- ``FlowceptAnthropicClient(client)`` — wrap an existing
  ``anthropic.Anthropic`` client to intercept all ``messages.create`` /
  ``stream`` calls.
- ``run_team(team, task, ...)`` *(AutoGen only)* — run an AutoGen team and
  capture full provenance.

For example: ``from flowcept.agents.academy.academy_plugin import openai_chat``.

Per-plugin reference
--------------------

Academy
~~~~~~~

``flowcept.agents.academy.academy_plugin.FlowceptAcademyPlugin`` wraps Academy
agents automatically and records ``@action`` and ``@loop`` executions.

Record hierarchy: campaign ``WorkflowObject`` → agent ``WorkflowObject`` →
``academy_action`` / ``academy_loop`` / ``academy_lifecycle`` task records
(siblings), with ``llm_call`` records nested under the action or loop that
issued them.

Two ``contextvars.ContextVar`` values are set automatically during execution
and can be read from user code:

- ``_current_academy_agent_id`` — the Academy agent identifier, set once per
  agent at startup.
- ``_current_action_task_id`` — the Flowcept ``task_id`` of the
  currently-executing ``@action`` or ``@loop``.

AutoGen
~~~~~~~

``flowcept.agents.autogen.autogen_plugin.FlowceptAutoGenPlugin`` wraps AutoGen
teams automatically. The module also exports ``run_team(team, task, ...)``,
which runs a team and captures full provenance, and ``FlowceptModelClient``,
a model-client wrapper.

Record hierarchy: ``WorkflowObject`` → ``autogen_run`` → ``autogen_message``
→ ``llm_call``.

CrewAI
~~~~~~

``flowcept.agents.crewai.crewai_plugin.FlowceptCrewAIPlugin`` records crew,
task, and agent executions through CrewAI's event listener and hook
interfaces (no automatic agent wrapping is needed or performed).

Record hierarchy: ``WorkflowObject`` → ``crewai_crew`` (no children via
``parent_task_id``); ``crewai_task`` → ``crewai_agent`` → ``llm_call`` /
``tool_call``.

LangChain
~~~~~~~~~

``flowcept.agents.langchain.langchain_plugin.FlowceptCallbackHandler`` is a
LangChain callback handler that records each root chain/graph run as a turn,
plus the model and tool calls inside it. Pass it wherever LangChain accepts
callbacks:

.. code-block:: python

   from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler

   graph.invoke(state, config={"callbacks": [FlowceptCallbackHandler(session_id="thread-42")]})

Records go to the harness session buffer (see :doc:`harness_plugins` for the
record model and where records are written).

LangGraph
~~~~~~~~~

``flowcept.agents.langgraph.langgraph_plugin.FlowceptLangGraphPlugin`` records
graph and node executions through a LangGraph/LangChain callback exposed as
``plugin.callback_handler``:

.. code-block:: python

   result = graph.invoke(state, config={"callbacks": [plugin.callback_handler]})

Record hierarchy: ``WorkflowObject`` → ``langgraph_graph`` →
``langgraph_node`` → ``llm_call`` / ``tool_call``.

OpenAI Agents SDK
~~~~~~~~~~~~~~~~~

``flowcept.agents.openai_agents.openai_agents_plugin`` provides
``FlowceptTraceProcessor``, a tracing processor for the OpenAI Agents SDK.
Register it once and nothing else changes:

.. code-block:: python

   from flowcept.agents.openai_agents.openai_agents_plugin import install

   install()

Like the LangChain handler, it records into the harness session buffer
(see :doc:`harness_plugins`).

What gets captured
------------------

For the four framework plugins (Academy, LangGraph, CrewAI, AutoGen):

.. list-table::
   :header-rows: 1

   * - Captured field
     - Academy
     - LangGraph
     - CrewAI
     - AutoGen
   * - Agent action / node executions
     - ✓
     - ✓
     - ✓
     - ✓
   * - Inputs and outputs per action
     - ✓
     - ✓
     - ✓
     - ✓
   * - Timing (start / end / latency)
     - ✓
     - ✓
     - ✓
     - ✓
   * - Parent–child task linkage
     - ✓
     - ✓
     - ✓
     - ✓
   * - LLM calls (OpenAI and Anthropic)
     - ✓
     - ✓
     - ✓
     - ✓
   * - Token usage
     - ✓
     - ✓
     - ✓
     - ✓
   * - Agent ID on LLM calls
     - ✓
     - ✓
     - ✓
     - ✓
   * - Automatic agent wrapping
     - ✓
     - ✓
     - —
     - ✓

Each plugin emits typed ``TaskObject`` records tagged with a ``subtype``
field, forming a nested provenance hierarchy (see the per-plugin sections
above for each hierarchy). All records carry ``campaign_id``,
``workflow_id``, ``task_id``, ``started_at``, ``ended_at``, and ``status``.
``used`` (inputs) and ``generated`` (outputs) are present on records that
represent computation (``academy_action``, node/graph records, LLM and tool
calls); ``parent_task_id`` links child records to their enclosing parent.

Cross-plugin composition
------------------------

The Academy, LangGraph, CrewAI, and AutoGen plugins can run under a **shared
campaign** using the ``from_academy_plugin()`` factory. AutoGen and CrewAI
share the Academy plugin's in-memory buffer directly; LangGraph creates its
own interceptor but inherits the same ``campaign_id``:

.. code-block:: python

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

Every record across all four plugins carries the same ``campaign_id``, so a
single query retrieves the full cross-framework provenance trace.

Cross-framework provenance linking
----------------------------------

When an Academy ``@action`` launches a LangGraph graph or an AutoGen team, the
plugins can record an explicit parent–child edge across framework boundaries.

**Academy (source side)** — read the enclosing task's identifier inside an
action:

.. code-block:: python

   from flowcept.agents.academy.academy_plugin import _current_action_task_id

   action_task_id = _current_action_task_id.get()

**LangGraph (target side)** — pass the action's ``task_id`` as
``_source_agent_id`` in the initial graph state:

.. code-block:: python

   result = await graph.ainvoke(
       {"_source_agent_id": action_task_id, ...},
       config={"callbacks": [lg.callback_handler]},
   )

The LangGraph plugin stores it as ``source_agent_id`` in ``custom_metadata``
of both ``langgraph_graph`` and ``langgraph_node`` records.

**AutoGen (target side)** — pass it as ``source_agent_id`` to ``run_team()``:

.. code-block:: python

   result = await ag.run_team(team, task, source_agent_id=action_task_id)

The AutoGen plugin stores it in ``custom_metadata`` of the ``autogen_run``
record.

In all cases, ``campaign_id`` and ``workflow_id`` alone are sufficient for
coarse-grained cross-framework queries without explicit identifier threading.

Examples
--------

Runnable examples for each framework are in
`examples/agents/ <https://github.com/ORNL/flowcept/tree/main/examples/agents>`_:

- ``examples/agents/academy/academy_example.py``
- ``examples/agents/langgraph/langgraph_example.py``
- ``examples/agents/crewai/crewai_example.py``
- ``examples/agents/autogen/autogen_example.py``
- ``examples/agents/combined_agentic_systems/combined_example.py`` — all four
  frameworks running concurrently under one campaign
