Telemetry Capture
=================

.. toctree::
   :maxdepth: 2
   :caption: Contents:

Telemetry in Flowcept refers to **runtime resource measurements** (CPU, memory, disk, network, GPU, process info, etc.)
collected alongside provenance. These measurements are crucial for **performance characterization** and for making
provenance more actionable in scientific workflows.

Flowcept captures telemetry **at the beginning and at the end of each provenance task**, so you can correlate resource
usage with inputs/outputs, status, timing, and hierarchy (parent/child tasks, loops, model layers, etc.).

- Telemetry objects are represented by :class:`flowcept.commons.flowcept_dataclasses.telemetry.Telemetry`.
- Decorated tasks use :func:`flowcept.instrumentation.flowcept_task.flowcept_task` and store telemetry in
  ``telemetry_at_start`` / ``telemetry_at_end`` fields of the :class:`flowcept.commons.flowcept_dataclasses.task_object.TaskObject`.
- PyTorch instrumentation via :func:`flowcept.instrumentation.flowcept_torch.flowcept_torch` also records telemetry for
  model parent/child forwards depending on configuration.

Configuration (per-type toggles)
--------------------------------

Telemetry capture is configured in your ``settings.yaml``. Each telemetry type can be independently turned on/off.

.. code-block:: yaml

   telemetry_capture:  # Toggle each telemetry type
     gpu: ~            # ~ means None (disabled). To enable, provide a list (see GPU section below).
     cpu: true
     per_cpu: true
     process_info: true
     mem: true
     disk: true
     network: true
     machine_info: true

   instrumentation:
     enabled: true
     torch:
       what: parent_and_children
       children_mode: telemetry_and_tensor_inspection
       epoch_loop: lightweight
       batch_loop: lightweight
       capture_epochs_at_every: 1
       register_workflow: true

**Notes**

- If a type is false or ``~``, Flowcept skips collecting it.
- GPU is **special**: enable it by providing a list of metrics (AMD and NVIDIA differ; see below).

How telemetry attaches to provenance
------------------------------------

Every provenance task includes telemetry fields when enabled:

- ``telemetry_at_start``: collected just before the task runs
- ``telemetry_at_end``: collected immediately after the task finishes

Example with the task decorator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

   from flowcept import Flowcept
   from flowcept.instrumentation.flowcept_task import flowcept_task

   @flowcept_task(output_names="y")
   def mult_two(x: int) -> int:
       return 2 * x

   with Flowcept(workflow_name="demo"):
       y = mult_two(21)

# The persisted task will include:
# - used/generated (inputs/outputs)
# - status, started_at/ended_at
# - telemetry_at_start / telemetry_at_end (if enabled)

Supported telemetry types
-------------------------

Flowcept uses the following libraries:

- ``psutil`` for CPU/memory/disk/network/process-info
- ``py-cpuinfo`` (``cpuinfo``) for CPU details in machine info
- ``pynvml`` for NVIDIA GPU metrics
- ``amdsmi`` (ROCm SMI Python) for AMD GPU metrics

.. note::
   Many telemetry fields are **platform-dependent**. Most keys mirror psutil outputs, so availability
   and naming can vary by OS and environment. Some fields may be missing depending on what psutil
   and vendor drivers can report.

CPU / per-CPU
~~~~~~~~~~~~~

**Keys (when enabled)**:

- ``cpu.times_avg`` — average CPU time breakdown across all CPUs (psutil ``cpu_times``).
- ``cpu.percent_all`` — total CPU utilization percent (psutil ``cpu_percent``).
- ``cpu.frequency`` — current CPU frequency in MHz (psutil ``cpu_freq().current``).
- ``cpu.times_per_cpu`` — per-CPU time breakdown list *(only if ``per_cpu: true``)*.
- ``cpu.percent_per_cpu`` — per-CPU utilization percent list *(only if ``per_cpu: true``)*.

``cpu.times_avg`` and ``cpu.times_per_cpu`` include psutil CPU time fields (platform dependent), such as:

- ``user`` — time spent in user mode.
- ``system`` — time spent in kernel mode.
- ``idle`` — time spent idle.
- ``nice`` — time spent on low-priority processes (Unix).
- ``iowait`` — time waiting for I/O (Unix).
- ``irq`` — time servicing hardware interrupts (Linux).
- ``softirq`` — time servicing software interrupts (Linux).
- ``steal`` — involuntary wait time in virtualized environments.
- ``guest`` — time running a guest OS (Linux).
- ``guest_nice`` — guest time with low priority (Linux).

See psutil CPU docs for full field availability: https://psutil.readthedocs.io/en/latest/#cpu

Process info
~~~~~~~~~~~~

**Keys (subset, platform-dependent)**:

- ``process.pid`` — OS process ID.
- ``process.cpu_number`` — current CPU core index.
- ``process.memory`` — process memory info (psutil ``memory_info``).
- ``process.memory_percent`` — percent of RAM used by the process.
- ``process.cpu_times`` — process CPU time breakdown (psutil ``cpu_times``).
- ``process.cpu_percent`` — process CPU utilization percent.
- ``process.io_counters`` — process I/O counters (if available).
- ``process.num_connections`` — number of open network connections.
- ``process.num_open_files`` — number of open file handles (where supported).
- ``process.num_open_file_descriptors`` — number of open file descriptors (Unix).
- ``process.num_threads`` — number of OS threads.
- ``process.num_ctx_switches`` — voluntary and involuntary context switches.
- ``process.executable`` — absolute path of the process executable.
- ``process.cmd_line`` — command line arguments for the process.

``process.memory`` includes psutil memory fields (platform dependent), such as:

- ``rss`` — resident set size (non-swapped physical memory).
- ``vms`` — virtual memory size.
- ``shared`` — shared memory (Linux).
- ``text`` — code segment size (Linux).
- ``lib`` — shared library size (Linux).
- ``data`` — data segment size (Linux).
- ``dirty`` — dirty pages (Linux).

``process.cpu_times`` includes psutil CPU time fields (platform dependent), such as:

- ``user`` — time spent in user mode by this process.
- ``system`` — time spent in kernel mode by this process.
- ``children_user`` — user time for child processes.
- ``children_system`` — system time for child processes.
- ``iowait`` — I/O wait time (Linux).

``process.io_counters`` includes psutil I/O fields (platform dependent), such as:

- ``read_count`` — read syscalls.
- ``write_count`` — write syscalls.
- ``read_bytes`` — bytes read.
- ``write_bytes`` — bytes written.
- ``read_chars`` — bytes read at the OS level.
- ``write_chars`` — bytes written at the OS level.

``process.num_ctx_switches`` includes:

- ``voluntary`` — voluntary context switches.
- ``involuntary`` — involuntary context switches.

See psutil process docs for full field availability: https://psutil.readthedocs.io/en/latest/#process-class

Memory
~~~~~~

**Keys**:

- ``memory.virtual`` — host virtual memory snapshot (psutil ``virtual_memory``).
- ``memory.swap`` — host swap memory snapshot (psutil ``swap_memory``).

``memory.virtual`` includes psutil memory fields (platform dependent), such as:

- ``total`` — total physical memory.
- ``available`` — available memory for new processes.
- ``percent`` — percent used.
- ``used`` — memory in use.
- ``free`` — memory not used.
- ``active`` — memory in active use.
- ``inactive`` — memory not recently used.
- ``buffers`` — buffers used by the OS (Linux).
- ``cached`` — cached files/pages (Linux).
- ``shared`` — memory shared across processes (Linux).
- ``slab`` — kernel slab memory (Linux).

``memory.swap`` includes psutil swap fields (platform dependent), such as:

- ``total`` — total swap space.
- ``used`` — used swap space.
- ``free`` — free swap space.
- ``percent`` — percent swap used.
- ``sin`` — bytes swapped in.
- ``sout`` — bytes swapped out.

See psutil memory docs for full field availability: https://psutil.readthedocs.io/en/latest/#memory

Disk
~~~~

**Keys**:

- ``disk.disk_usage`` — filesystem usage for ``/`` (psutil ``disk_usage``).
- ``disk.io_sum`` — aggregated disk I/O counters (psutil ``disk_io_counters(perdisk=False)``).
- ``disk.io_per_disk`` — per-device disk I/O counters (psutil ``disk_io_counters(perdisk=True)``).

``disk.disk_usage`` includes psutil disk usage fields:

- ``total`` — total space in bytes.
- ``used`` — used space in bytes.
- ``free`` — free space in bytes.
- ``percent`` — percent used.

``disk.io_sum`` and ``disk.io_per_disk`` include psutil disk I/O fields (platform dependent), such as:

- ``read_count`` — reads completed.
- ``write_count`` — writes completed.
- ``read_bytes`` — bytes read.
- ``write_bytes`` — bytes written.
- ``read_time`` — time spent reading (ms).
- ``write_time`` — time spent writing (ms).
- ``read_merged`` — merged reads (Linux).
- ``write_merged`` — merged writes (Linux).
- ``busy_time`` — time spent doing I/O (ms, Linux).

See psutil disk docs for full field availability: https://psutil.readthedocs.io/en/latest/#disks

Network
~~~~~~~

**Keys**:

- ``network.netio_sum`` — aggregated network I/O counters (psutil ``net_io_counters(pernic=False)``).
- ``network.netio_per_interface`` — per-interface I/O counters (psutil ``net_io_counters(pernic=True)``).

``network.netio_sum`` and ``network.netio_per_interface`` include psutil network fields (platform dependent), such as:

- ``bytes_sent`` — bytes sent.
- ``bytes_recv`` — bytes received.
- ``packets_sent`` — packets sent.
- ``packets_recv`` — packets received.
- ``errin`` — inbound errors.
- ``errout`` — outbound errors.
- ``dropin`` — inbound drops.
- ``dropout`` — outbound drops.

See psutil network docs for full field availability: https://psutil.readthedocs.io/en/latest/#network

Machine info (snapshot)
~~~~~~~~~~~~~~~~~~~~~~~

If ``machine_info: true``, :meth:`flowcept.instrumentation.telemetry.TelemetryCapture.capture_machine_info`
returns a **snapshot** with:

- platform info (``platform.uname``), CPU info (``cpuinfo``), environment variables
- memory (virtual/swap), disk usage, NIC addresses
- hostname (``HOSTNAME``), login name (``LOGIN_NAME``)
- process info (same structure as above)
- optional GPU block (if GPU telemetry is on)

``platform`` includes:

- ``system`` — OS name (e.g., Linux, Darwin, Windows).
- ``node`` — network name (hostname).
- ``release`` — OS release version.
- ``version`` — OS version string.
- ``machine`` — machine type (e.g., x86_64).
- ``processor`` — CPU identifier string.

``network`` is derived from ``psutil.net_if_addrs`` and includes:

- ``family`` — address family (AF_INET, AF_INET6, etc.).
- ``address`` — IP or MAC address.
- ``netmask`` — netmask.
- ``broadcast`` — broadcast address (if any).
- ``ptp`` — point-to-point address (if any).

``cpu`` is the raw dict returned by ``cpuinfo.get_cpu_info`` (py-cpuinfo). See:
https://py-cpuinfo.readthedocs.io/en/latest/

See psutil network address docs for full field availability: https://psutil.readthedocs.io/en/latest/#psutil.net_if_addrs

GPU telemetry
-------------

Enable GPU by setting ``telemetry_capture.gpu`` to a **list of metrics**. Flowcept will try AMD first, then NVIDIA:

- AMD visibility via ``ROCR_VISIBLE_DEVICES``
- NVIDIA visibility via ``CUDA_VISIBLE_DEVICES`` or NVML detection

Common behavior:

- Flowcept enumerates visible GPUs and collects metrics per device: ``gpu.gpu_0``, ``gpu.gpu_1``, …
- Which fields are collected depends on vendor **and** your configured metric list.

AMD (ROCm SMI)
~~~~~~~~~~~~~~

**Supported metric names** (choose any subset in the list):

- ``used`` — VRAM usage for the device (``amdsmi_get_gpu_memory_usage``).
- ``activity`` — current GPU activity percent (``amdsmi_get_gpu_activity``).
- ``power.average_socket_power`` — average socket power draw.
- ``power.energy_accumulator`` — cumulative energy use.
- ``temperature.edge`` — edge temperature.
- ``temperature.hotspot`` — hotspot temperature.
- ``temperature.mem`` — memory temperature.
- ``temperature.vrgfx`` — VR graphics temperature.
- ``temperature.vrmem`` — VR memory temperature.
- ``temperature.hbm`` — HBM temperature.
- ``temperature.fan_speed`` — current fan speed.
- ``others.current_gfxclk`` — current graphics clock.
- ``others.current_socclk`` — current SoC clock.
- ``others.current_uclk`` — current memory clock.
- ``others.current_vclk0`` — current video clock.
- ``others.current_dclk0`` — current display clock.
- ``id`` — device UUID.
- ``gpu_ix`` — device index (added by Flowcept for AMD).

Example (enable AMD GPU capture):

.. code-block:: yaml

   telemetry_capture:
     gpu: ["used", "activity", "power", "temperature", "id"]

NVIDIA (NVML)
~~~~~~~~~~~~~

**Supported metric names** (choose any subset in the list):

- ``used`` — device memory used in bytes (``nvmlDeviceGetMemoryInfo``).
- ``temperature`` — GPU temperature in Celsius (``nvmlDeviceGetTemperature``).
- ``power`` — power usage in milliwatts (``nvmlDeviceGetPowerUsage``).
- ``name`` — device name (``nvmlDeviceGetName``).
- ``id`` — device UUID (``nvmlDeviceGetUUID``).

Example (enable NVIDIA GPU capture):

.. code-block:: yaml

   telemetry_capture:
     gpu: ["used", "temperature", "power", "name", "id"]

PyTorch model telemetry
-----------------------

Use :func:`flowcept.instrumentation.flowcept_torch.flowcept_torch` to instrument a ``torch.nn.Module``:

- Parent module ``forward`` can record telemetry and tensor inspections depending on config.
- Child modules (layers) can also record telemetry/tensors when ``what: parent_and_children`` and an appropriate
  ``children_mode`` are set.
- Flowcept can create **epoch** and **batch** loop tasks (lightweight or default), maintaining parent/child IDs so all
  forward calls are linked.

Configuration
~~~~~~~~~~~~~

.. code-block:: yaml

   instrumentation:
     enabled: true
     torch:
       what: parent_and_children                # or "parent_only"
       children_mode: telemetry_and_tensor_inspection  # "telemetry", "tensor_inspection", or both
       epoch_loop: lightweight                  # or default / ~ (disable)
       batch_loop: lightweight                  # or default / ~ (disable)
       capture_epochs_at_every: 1               # capture every N epochs
       register_workflow: true                  # save model as a workflow

Minimal example
~~~~~~~~~~~~~~~

.. code-block:: python

   import torch
   import torch.nn as nn
   from flowcept import Flowcept
   from flowcept.instrumentation.flowcept_torch import flowcept_torch

   @flowcept_torch
   class MyNet(nn.Module):
       def __init__(self, **kwargs):
           super().__init__()
           self.fc = nn.Linear(10, 1)

       def forward(self, x):
           return self.fc(x)

   x = torch.randn(8, 10)
   model = MyNet(get_profile=True)   # optional: profile model (params, widths, modules)

   with Flowcept(workflow_name="torch_demo"):
       y = model(x)                   # parent forward + (optionally) child forwards recorded
                                      # telemetry recorded per config

What gets stored
~~~~~~~~~~~~~~~~

- Parent/child forward tasks include:
  - ``subtype`` (e.g., ``parent_forward`` or ``child_forward``)
  - ``parent_task_id`` linkage
  - optional tensor inspections (shape, device, nbytes, density)
  - ``telemetry_at_end`` (if telemetry is enabled)
- Optional workflow registration for the model with profile (params, max width, module tree).

Direct access to Telemetry objects
----------------------------------

If you need to call the capture API yourself:

.. code-block:: python

   from flowcept.instrumentation.telemetry import TelemetryCapture
   tel = TelemetryCapture().capture()
   if tel:
       print(tel.to_dict())  # same structure stored in tasks

Practical tips
--------------

- Turn off types you don’t need; telemetry can add overhead on very tight loops.
- GPU capture requires vendor libraries:
  - AMD: ``amdsmi`` (ROCm SMI Python)
  - NVIDIA: ``pynvml``
- Use environment variables to control visible devices:
  - ``ROCR_VISIBLE_DEVICES`` (AMD)
  - ``CUDA_VISIBLE_DEVICES`` (NVIDIA)
- For PyTorch large models, prefer ``children_mode: telemetry`` if tensor inspection is too heavy; or
  use ``epoch_loop: lightweight`` + ``batch_loop: lightweight`` to keep loop overhead minimal.

Reference
---------

- Telemetry container: :class:`flowcept.commons.flowcept_dataclasses.telemetry.Telemetry`
- Task decorator: :func:`flowcept.instrumentation.flowcept_task.flowcept_task`
- PyTorch decorator: :func:`flowcept.instrumentation.flowcept_torch.flowcept_torch`
- Telemetry capture impl: :class:`flowcept.instrumentation.telemetry.TelemetryCapture`
