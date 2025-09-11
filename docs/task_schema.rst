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
Each is a dictionary with the following structure:

CPU
~~~

- **times_avg**: Dictionary with CPU times
  - **user**, **nice**, **system**, **idle**
- **percent_all**: Overall CPU usage percentage
- **frequency**: CPU frequency
- **times_per_cpu**: List of dictionaries of per-core times
- **percent_per_cpu**: List of per-core usage percentages

Process
~~~~~~~

- **pid**: Process ID
- **memory**: Dictionary with memory stats
  - **rss**, **vms**, **pfaults**, **pageins**
- **memory_percent**: Memory usage percentage
- **cpu_times**: Dictionary with CPU times
  - **user**, **system**, **children_user**, **children_system**
- **cpu_percent**: CPU usage percentage
- **executable**: Path to executable
- **cmd_line**: Command line arguments
- **num_open_file_descriptors**, **num_connections**, **num_open_files**, **num_threads**
- **num_ctx_switches**: Dictionary with
  - **voluntary**, **involuntary**

Memory
~~~~~~

- **virtual**: Dictionary with virtual memory stats
  - **total**, **available**, **percent**, **used**, **free**, **active**, **inactive**, **wired**
- **swap**: Dictionary with swap memory stats
  - **total**, **used**, **free**, **percent**, **sin**, **sout**

Disk
~~~~

- **disk_usage**: Dictionary with usage stats
  - **total**, **used**, **free**, **percent**
- **io_sum**: Dictionary with I/O stats
  - **read_count**, **write_count**, **read_bytes**, **write_bytes**, **read_time**, **write_time**

Network
~~~~~~~

- **netio_sum**: Dictionary with aggregate network I/O
  - **bytes_sent**, **bytes_recv**, **packets_sent**, **packets_recv**, **errin**, **errout**, **dropin**, **dropout**
- **netio_per_interface**: Dictionary keyed by interface with same metrics

GPU
~~~

GPU telemetry data, if available, is in the ``gpu`` field. Structure depends on vendor.

**Common Fields**

- **gpu_ix**: GPU index (int)
- **used**: Memory used (bytes)
- **temperature**: Dictionary or integer temperature
- **power**: Dictionary or value of power usage
- **id**: Device UUID
- **name**: GPU name (NVIDIA only)
- **activity**: GPU activity percentage (AMD only)
- **others**: Clock/performance data (AMD only)

**AMD GPU**

- **temperature**: edge, hotspot, mem, vrgfx, vrmem, hbm, fan_speed
- **power**: average_socket_power, energy_accumulator
- **others**: current_gfxclk, current_socclk, current_uclk, current_vclk0, current_dclk0

**NVIDIA GPU**

- **temperature**: Celsius value
- **power**: Milliwatts usage
- **used**: Memory used (bytes)
- **name**: Model name
- **id**: Device UUID

Notes
-----

Telemetry values vary depending on system capabilities, GPU vendor APIs, 
and what is enabled in the configuration.
