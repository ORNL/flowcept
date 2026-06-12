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

Task-Centric Design and Agent Modeling
--------------------------------------
Flowcept is fundamentally task-centric: everything is built around the Task record. Rather than maintaining complex relational entities for all components, Flowcept uses a simple, implicit schema to represent workflows and agents:

* **Workflows**: A workflow class (identified by its name) can have multiple executions (identified by ``workflow_id``). Tasks carry ``workflow_id`` to link executions, while Workflow objects store the static metadata (like names and descriptions).
* **Agents**: Similarly, an agent class (identified by its ``agent_name``) can have multiple instantiations (identified by ``agent_id``). Tasks carry ``agent_id`` and ``agent_name`` (as well as ``source_agent_id`` and ``source_agent_name``) directly.
* **Campaigns**: Unlike workflows and agents, campaigns are more static; they are identified simply by ``campaign_id`` and do not change frequently over time.

.. note::
   This task-centric layout keeps storage requirements simple and highly efficient. In the future, we may introduce a more dedicated, first-class schema and storage path for agents, similar to how tasks, workflows, and artifacts are structured.

Figure
------
.. only:: html

   .. figure:: img/PROV-AGENT.svg
      :width: 100%
      :alt: PROV-AGENT overview

      PROV-AGENT overview. Dashed arrows denote *subClassOf*.
