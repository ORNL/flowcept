Task Data Schema
================

This document describes the schema of a task record used to capture metadata, telemetry, and provenance information in a workflow. Each task captures input parameters, execution metadata, and system-level telemetry data at the start and end of its execution.

Task Fields
-----------

- **task_id**: Unique identifier for the task (string)
- **activity_id**: Identifier for the type of activity performed by the task (string)
- **workflow_id**: Identifier for the workflow this task belongs to (string)
- **campaign_id**: Identifier for the campaign this task belongs to (string)
- **used**: Input parameters used by the task (dictionary)
- **started_at**: Timestamp when the task started (datetime)
- **telemetry_at_start**: System telemetry data collected at the start of the task (dictionary)
- **status**: Current status of the task (string)
- **ended_at**: Timestamp when the task ended (datetime)
- **telemetry_at_end**: System telemetry data collected at the end of the task (dictionary)
- **generated**: Output generated by the task (dictionary)
- **node_name**: Name of the node where the task executed (string)
- **login_name**: Login name of the user who executed the task (string)
- **hostname**: Hostname of the machine where the task executed (string)
- **finished**: Boolean indicating whether the task has finished (boolean)
- **registered_at**: Timestamp when the task was registered (datetime)

Telemetry Data Schema
---------------------

If telemetry data capture is enabled, telemetry data is captured both at the start and end of the task execution under the fields `telemetry_at_start` and `telemetry_at_end`. These fields are dictionaries that may include the following subfields:

**cpu**:
  - **times_avg**: (dictionary)
    - **user**: User CPU time
    - **nice**: Nice CPU time
    - **system**: System CPU time
    - **idle**: Idle CPU time
  - **percent_all**: Overall CPU usage percentage
  - **frequency**: CPU frequency
  - **times_per_cpu**: List of CPU times per core (list of dictionaries)
  - **percent_per_cpu**: List of CPU usage percentages per core

**process**:
  - **pid**: Process ID
  - **memory**: (dictionary)
    - **rss**: Resident Set Size
    - **vms**: Virtual Memory Size
    - **pfaults**: Page faults
    - **pageins**: Page ins
  - **memory_percent**: Memory usage percentage
  - **cpu_times**: (dictionary)
    - **user**: User CPU time
    - **system**: System CPU time
    - **children_user**: User CPU time for children
    - **children_system**: System CPU time for children
  - **cpu_percent**: CPU usage percentage
  - **executable**: Executable path
  - **cmd_line**: Command line arguments
  - **num_open_file_descriptors**: Number of open file descriptors
  - **num_connections**: Number of network connections
  - **num_open_files**: Number of open files
  - **num_threads**: Number of threads
  - **num_ctx_switches**: (dictionary)
    - **voluntary**: Voluntary context switches
    - **involuntary**: Involuntary context switches

**memory**:
  - **virtual**: (dictionary)
    - **total**, **available**, **percent**, **used**, **free**, **active**, **inactive**, **wired**
  - **swap**: (dictionary)
    - **total**, **used**, **free**, **percent**, **sin**, **sout**

**disk**:
  - **disk_usage**: (dictionary)
    - **total**, **used**, **free**, **percent**
  - **io_sum**: (dictionary)
    - **read_count**, **write_count**, **read_bytes**, **write_bytes**, **read_time**, **write_time**

**network**:
  - **netio_sum**: (dictionary)
    - **bytes_sent**, **bytes_recv**, **packets_sent**, **packets_recv**, **errin**, **errout**, **dropin**, **dropout**
  - **netio_per_interface**: Dictionary of interface-specific I/O metrics

**gpu**:
  GPU telemetry data, if available, is stored in the `gpu` field. Its structure varies based on the vendor:

  - **Common Fields**

    - **gpu_ix**: Index of the GPU used (int)
    - **used**: Memory used (bytes)
    - **temperature**: Dictionary of temperature data or int (see below)
    - **power**: Dictionary or value representing power usage
    - **id**: Device UUID
    - **name** (NVIDIA only): GPU name
    - **activity** (AMD only): GPU activity percentage
    - **others** (AMD only): Additional clock and performance data

  - **AMD GPU**:

    - **temperature**:
      - edge, hotspot, mem, vrgfx, vrmem, hbm, fan_speed
    - **power**:
      - average_socket_power, energy_accumulator
    - **others**:
      - current_gfxclk, current_socclk, current_uclk, current_vclk0, current_dclk0

  - **NVIDIA GPU**:

    - **temperature**: GPU temperature in Celsius
    - **power**: Power usage in milliwatts
    - **used**: Memory used in bytes
    - **name**: GPU model name
    - **id**: Device UUID

Telemetry values may vary depending on system capabilities, what is available in the GPU API, and what is enable in the settings.yaml file.
