Data Schemas
===============

Data Schemas for Flowcept data.

.. toctree::
   :maxdepth: 1
   :caption: Schemas:

   task_schema
   workflow_schema

PROV-AGENT and Flowcept
=======================

PROV-AGENT is a lightweight extension of `W3C PROV <https://www.w3.org/TR/prov-dm/>`_ for agentic workflows. It names the
main building blocks you see in modern AI systems:

- **Activities** such as Campaign, Workflow, and Task
- **Agents** such as an AI agent or a human user
- **Data Objects** such as domain data, prompts, responses, scheduling info, and telemetry
- **Relations** such as *used*, *wasGeneratedBy*, *wasAssociatedWith*, *wasAttributedTo*, and *wasInformedBy*

The goal is to keep agent interactions, model calls, and traditional tasks in one connected provenance graph.

How Flowcept represents PROV-AGENT
----------------------------------
Flowcept stores provenance according to PROV-AGENT, but keeps the storage model simple.
Everything is captured with **two record types**:

- **Workflow**: high-level run context, user and environment info, and workflow-level inputs and outputs.
- **Task**: units of work with inputs, outputs, timing, telemetry, and links to other tasks and agents.

At a high level:

- **Activities** map to the *Workflow* and *Task* records.
- **Agents** attach to those records through simple fields, for example an agent identifier.
- **Data Objects** live inside the records, most often in ``used`` and ``generated`` or in small structured blocks
  like telemetry and scheduling.
- **Relations** are preserved with IDs and standard fields (for example, workflow IDs, parent or dependency links),
  so the graph remains connected and queryable.

Figure
------
.. only:: html

   .. figure:: img/PROV-AGENT.svg
      :width: 100%
      :alt: PROV-AGENT overview

      PROV-AGENT overview. Dashed arrows denote *subClassOf*.
