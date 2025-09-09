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

CPU / per-CPU
~~~~~~~~~~~~~

**Keys (when enabled)**:

- ``cpu.times_avg`` — average CPU times (psutil)
- ``cpu.percent_all`` — overall CPU % (psutil)
- ``cpu.frequency`` — current CPU frequency (psutil)
- ``cpu.times_per_cpu`` — per-CPU times (psutil) *(only if ``per_cpu: true``)*
- ``cpu.percent_per_cpu`` — per-CPU % (psutil) *(only if ``per_cpu: true``)*

Process info
~~~~~~~~~~~~

**Keys (subset, platform-dependent)**:

- ``process.pid``, ``process.cpu_number``, ``process.memory`` / ``memory_percent``
- ``process.cpu_times`` / ``cpu_percent``
- ``process.io_counters`` (if available)
- ``process.num_connections``, ``num_open_files``, ``num_threads``, ``num_ctx_switches``
- ``process.executable``, ``process.cmd_line``

Memory
~~~~~~

**Keys**:

- ``memory.virtual`` (psutil ``virtual_memory``)
- ``memory.swap`` (psutil ``swap_memory``)

Disk
~~~~

**Keys**:

- ``disk.disk_usage`` (psutil ``disk_usage("/")``)
- ``disk.io_sum`` (psutil ``disk_io_counters(perdisk=False)``)
- ``disk.io_per_disk`` (psutil ``disk_io_counters(perdisk=True)``)

Network
~~~~~~~

**Keys**:

- ``network.netio_sum`` (psutil ``net_io_counters(pernic=False)``)
- ``network.netio_per_interface`` (psutil per-NIC counters)

Machine info (snapshot)
~~~~~~~~~~~~~~~~~~~~~~~

If ``machine_info: true``, :meth:`flowcept.instrumentation.telemetry.TelemetryCapture.capture_machine_info`
returns a **snapshot** with:

- platform info (``platform.uname``), CPU info (``cpuinfo``), environment variables
- memory (virtual/swap), disk usage, NIC addresses
- hostname (``HOSTNAME``), login name (``LOGIN_NAME``)
- process info (same structure as above)
- optional GPU block (if GPU telemetry is on)

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

- ``used`` — VRAM usage (``amdsmi_get_gpu_memory_usage``)
- ``activity`` — current GPU activity (``amdsmi_get_gpu_activity``)
- ``power`` — average socket power, energy accumulator (from ``amdsmi_get_gpu_metrics_info``)
- ``temperature`` — edge, hotspot, memory, VR*, HBM, fan speed (from metrics info)
- ``others`` — selected clocks (gfxclk/socclk/uclk/vclk0/dclk0) (from metrics info)
- ``id`` — device UUID

Example (enable AMD GPU capture):

.. code-block:: yaml

   telemetry_capture:
     gpu: ["used", "activity", "power", "temperature", "id"]

NVIDIA (NVML)
~~~~~~~~~~~~~

**Supported metric names** (choose any subset in the list):

- ``used`` — device memory used (``nvmlDeviceGetMemoryInfo``)
- ``temperature`` — GPU temperature (``nvmlDeviceGetTemperature``)
- ``power`` — power usage (``nvmlDeviceGetPowerUsage``)
- ``name`` — device name (``nvmlDeviceGetName``)
- ``id`` — UUID (``nvmlDeviceGetUUID``)

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
