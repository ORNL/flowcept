Workflow Data Schema
====================

A workflow record captures high-level metadata for one Flowcept-enabled run.
It is represented in code by :class:`flowcept.commons.flowcept_dataclasses.workflow_object.WorkflowObject`.

Record Type
-----------

- **type** (str): Constant message label, always ``"workflow"`` when serialized.

Identifiers
-----------

- **workflow_id** (str): Unique identifier for this workflow execution.
- **parent_workflow_id** (str): Parent workflow identifier, if this workflow is nested.
- **campaign_id** (str): Campaign identifier grouping related workflows.
- **adapter_id** (str): Adapter that triggered workflow capture, such as ``dask``.
- **interceptor_ids** (list[str]): Interceptor instance identifiers associated with this workflow.
- **agent_id** (str): Agent identifier associated with this workflow, when applicable.

User-Facing Metadata
--------------------

- **name** (str): Human-readable workflow name.
- **workflow_description** (str): Human-readable description of what the workflow is about.
- **subtype** (str): Optional workflow category, such as ``ml_workflow`` or ``data_prep_workflow``.
- **custom_metadata** (dict): User-defined workflow metadata.

Inputs, Outputs, and Repository
-------------------------------

- **used** (dict): Workflow-level inputs, arguments, datasets, or configuration values.
- **generated** (dict): Workflow-level outputs, artifacts, models, or summary results.
- **code_repository** (dict): Repository metadata captured during enrichment, such as commit SHA, branch, root, remote, and dirty state.

Runtime Context
---------------

- **machine_info** (dict): System and hardware information where the workflow executed.
- **conf** (dict): Flowcept runtime configuration metadata. Currently includes ``settings_path``.
- **flowcept_settings** (dict): Snapshot of active Flowcept settings.
- **flowcept_version** (str): Flowcept package version used during execution.
- **utc_timestamp** (float): UTC timestamp when the workflow object was created.
- **user** (str): User who launched or owns the workflow run.
- **environment_id** (str): Runtime environment identifier from settings, when available.
- **sys_name** (str): Logical system or facility name.
- **extra_metadata** (dict): Extra metadata from settings.

Notes
-----

- ``WorkflowObject.to_dict()`` omits fields whose value is ``None``.
- ``WorkflowObject.enrich()`` adds settings, version, timestamp, user, system, extra metadata, and optional Git metadata.
- ``used`` and ``generated`` support workflow-level lineage and can contain structured or semi-structured values.
