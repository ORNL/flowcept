Task Data Schema
================

This document describes the schema of a task record used to capture metadata, telemetry, and provenance in a workflow. 
A task represents one unit of work, including inputs, outputs, execution context, system telemetry, and runtime provenance.

Each task record may include fields for identifiers, timing, telemetry, user and system context, dependencies, and custom metadata.

Task Fields
-----------

- **type**: Constant type label (``"task"``) (string)
- **subtype**: Optional subtype of the task, e.g., iteration, ML step, custom (string)

Identifiers
~~~~~~~~~~~

- **task_id**: Unique identifier for the task (string)
- **workflow_id**: Identifier for the workflow this task belongs to (string)
- **workflow_name**: Name of the workflow this task belongs to (string)
- **campaign_id**: Identifier for the campaign this task belongs to (string)
- **activity_id**: Identifier for the activity performed by the task (usually a function name) (string)
- **group_id**: Identifier grouping related tasks, e.g., loop iterations (string)
- **parent_task_id**: Identifier of the parent task, if nested (string)
- **agent_id**: Identifier of the agent responsible for executing the task (string)
- **source_agent_id**: Identifier of the agent that sent this task for execution (string)
- **adapter_id**: Identifier of the adapter that produced this task (string)
- **environment_id**: Identifier of the environment where the task ran (string)

Timing
~~~~~~

- **utc_timestamp**: UTC timestamp when the task object was created (float)
- **submitted_at**: Timestamp when the task was submitted (float)
- **started_at**: Timestamp when execution started (float)
- **ended_at**: Timestamp when execution ended (float)
- **registered_at**: Timestamp when registered in storage (float)

Provenance Data
~~~~~~~~~~~~~~~

- **used**: Inputs consumed by the task, such as parameters, files, or resources (dictionary)
- **generated**: Outputs produced by the task, e.g., results, artifacts, files (dictionary)
- **dependencies**: List of task IDs this task depends on (list)
- **dependents**: List of task IDs that depend on this task (list)

Execution Metadata
~~~~~~~~~~~~~~~~~~

- **status**: Execution status of the task (e.g., FINISHED, ERROR) (string)
- **stdout**: Captured standard output (string or dictionary)
- **stderr**: Captured standard error (string or dictionary)
- **data**: Arbitrary raw payload associated with the task (any type)
- **custom_metadata**: User- or developer-provided metadata dictionary (dictionary)
- **tags**: User-defined tags attached to the task (list)

User and System Context
~~~~~~~~~~~~~~~~~~~~~~~

- **user**: User who executed or triggered the task (string)
- **login_name**: Login name of the user in the environment (string)
- **node_name**: Node where the task executed (string)
- **hostname**: Hostname of the machine executing the task (string)
- **public_ip**: Public IP address (string)
- **private_ip**: Private IP address (string)
- **address**: Optional network address (string)
- **mq_host**: Message queue host associated with the task (string)

Telemetry Data Schema
---------------------

If telemetry capture is enabled, telemetry snapshots are stored in ``telemetry_at_start`` and ``telemetry_at_end``. 
Each is a dictionary created from :class:`flowcept.commons.flowcept_dataclasses.telemetry.Telemetry`, and includes
the enabled telemetry blocks (``cpu``, ``process``, ``memory``, ``disk``, ``network``, and optional ``gpu``).

For the complete list of telemetry keys and their meanings (including platform-dependent fields),
see `Telemetry capture <telemetry_capture.html>`_.

Notes
-----

Telemetry values vary depending on system capabilities, GPU vendor APIs, 
and what is enabled in the configuration.
