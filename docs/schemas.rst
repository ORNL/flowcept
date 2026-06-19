Data Schemas
===============

Data Schemas for Flowcept data.

.. toctree::
   :maxdepth: 1
   :caption: Schemas:

   task_schema
   workflow_schema
   blob_schema

PROV-AGENT and Flowcept
=======================

PROV-AGENT is a `W3C PROV <https://www.w3.org/TR/prov-dm/>`_ extension for capturing provenance of agentic AI workflows.
It is described in:

  R. Souza et al., *PROV-AGENT: PROV-AGENT: Unified Provenance for Tracking AI Agent Interactions in Agentic Workflows*,
  arXiv:2508.02866, 2025. https://arxiv.org/abs/2508.02866

PROV-AGENT names the main building blocks you see in modern AI systems:

- **Activities** such as Campaign, Workflow, Task, AIModelInvocation, and AgentTool
- **Agents** such as an AI agent or a human user
- **Data Objects** such as domain data, prompts, responses, scheduling info, and telemetry
- **Relations** such as *used*, *wasGeneratedBy*, *wasAssociatedWith*, *wasAttributedTo*, and *wasInformedBy*

The goal is to keep agent interactions, model calls, and traditional tasks in one connected provenance graph.

How Flowcept represents PROV-AGENT
----------------------------------
Flowcept stores provenance according to PROV-AGENT, but keeps the storage model simple.
Everything is captured with **three main record types**:

- **Workflow**: high-level run context, user and environment info, and workflow-level inputs and outputs.
- **Task**: units of work with inputs, outputs, timing, telemetry, and links to other tasks and agents.
- **Blob/Object**: metadata and linkage for stored binary payloads, datasets, models, artifacts, and input files.

At a high level:

- **Activities** map to the *Workflow* and *Task* records.
- **Agents** attach to those records through simple fields, for example an agent identifier.
- **Data Objects** live in ``used`` and ``generated`` for inline provenance values, or in the ``objects`` collection
  when Flowcept stores payload metadata through ``BlobObject``.
- **Relations** are preserved with IDs and standard fields (for example, workflow IDs, parent or dependency links),
  so the graph remains connected and queryable.

PROV-AGENT task subtypes
------------------------
The ``subtype`` field on a Task record narrows it to a specific PROV-AGENT activity class.
Use the :class:`~flowcept.commons.vocabulary.PROV_AGENT` enum to set these values:

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Enum value
     - Stored string
     - Description
   * - ``PROV_AGENT.AI_MODEL_INVOCATION``
     - ``ai_model_invocation``
     - A single LLM prompt→response call (*AIModelInvocation* in PROV-AGENT).
       Captured automatically by :class:`~flowcept.instrumentation.flowcept_agent_task.FlowceptLLM`.
       ``used.prompt`` stores the input; ``generated.response`` stores the output;
       ``custom_metadata.llm_usage`` stores token counts.
   * - ``PROV_AGENT.AGENT_TOOL``
     - ``agent_tool``
     - A tool execution by an AI agent (*AgentTool* in PROV-AGENT).
       Captured automatically by the
       :func:`~flowcept.instrumentation.flowcept_agent_task.agent_flowcept_task` decorator
       applied to MCP tools and LangGraph tool nodes.
       ``used`` stores tool arguments; ``generated`` stores the return value.

The ``wasInformedBy`` relation — an ``AgentTool`` activity informing an ``AIModelInvocation`` — is
the key link for root-cause analysis and downstream impact tracing in PROV-AGENT.  In Flowcept this
is expressed through the ``agent_id`` field: every task with the same ``agent_id`` belongs to the
same AI agent and can be queried together to reconstruct the full agent provenance graph.

The UI uses ``subtype`` to visually distinguish AI agent activities from regular workflow tasks.
Filter for ``subtype == "ai_model_invocation"`` or ``subtype == "agent_tool"`` to isolate agent
interactions from the provenance database.

Figure
------
.. only:: html

   .. figure:: img/PROV-AGENT.svg
      :width: 100%
      :alt: PROV-AGENT overview

      PROV-AGENT overview. Dashed arrows denote *subClassOf*.
