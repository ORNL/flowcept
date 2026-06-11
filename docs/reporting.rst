Reporting
=========

Flowcept can generate summarized reports from provenance records.

Current report implementations:

- ``report_type="provenance_card"`` with ``format="markdown"`` (**default**)
- ``report_type="provenance_report"`` with ``format="pdf"`` (executive PDF with plots)

The markdown workflow cards follow the upstream Workflow Provenance Card template:
`workflow-provenance-card <https://github.com/data-cards/workflow-provenance-card>`_.
Flowcept keeps its legacy timing, resource, and artifact summaries inside the template's
optional sections so the report stays compact without losing useful provenance detail.


API
---

Use:

.. code-block:: python

   from flowcept import Flowcept

   # Default path: markdown provenance card
   Flowcept.generate_report(
       report_type="provenance_card",
       format="markdown",
       output_path="PROVENANCE_CARD.md",
       records=my_records,  # or input_jsonl_path=..., or workflow_id/campaign_id
   )


Markdown Provenance Cards (Default)
-----------------------------------

Markdown provenance cards are the default reporting mode.

.. code-block:: python

   from flowcept import Flowcept

   # 1) Generate from workflow_id (DB-backed mode)
   Flowcept.generate_report(
       report_type="provenance_card",
       format="markdown",
       workflow_id="20c5939f-f3ee-4031-9303-a9e68a5a8092",
       output_path="PROVENANCE_CARD.md",
   )

   # 2) Generate from in-memory records
   Flowcept.generate_report(
       report_type="provenance_card",
       format="markdown",
       records=my_records,
       output_path="PROVENANCE_CARD_FROM_RECORDS.md",
   )

   # 3) Generate from Flowcept JSONL buffer
   Flowcept.generate_report(
       report_type="provenance_card",
       format="markdown",
       input_jsonl_path="/tmp/flowcept_buffer.jsonl",
       output_path="PROVENANCE_CARD_FROM_JSONL.md",
   )

Render Markdown Directly in Terminal (Rich)
-------------------------------------------

You can optionally print the generated markdown report in a rich terminal:

.. code-block:: python

   from flowcept import Flowcept

   Flowcept.generate_report(
       report_type="provenance_card",
       format="markdown",
       records=my_records,
       output_path="PROVENANCE_CARD.md",
       print_markdown=True,
   )

If Rich is not installed and ``print_markdown=True``, Flowcept raises an error.
Install Rich via:

.. code-block:: bash

   pip install flowcept["extras"]


Input Modes
-----------

Exactly one input mode must be provided:

- ``input_jsonl_path``: read from a Flowcept JSONL buffer file.
- ``records``: list of dictionaries already loaded in memory.
- ``workflow_id`` or ``campaign_id``: query workflow, task, and object documents from DB.


Aggregation
-----------

The provenance card is summarized, not raw-dump oriented.

- Grouping key: ``activity_id``.
- Per-group summary includes:
  - number of task records aggregated (``n_tasks``)
  - status counts
  - timing aggregates (median/summary fields)

This aggregation method is written in generated output under ``Aggregation Method``.


Object Metadata Summary
-----------------------

When objects are present, reports include metadata-only summaries:

- counts by type
- counts by storage mode (``in_object`` vs ``gridfs``)
- linkage counts (task/workflow-linked)
- object version and size summaries

Blob payload bytes are excluded from report rendering.


Real Example (Rendered in RST)
------------------------------

Below is a real example equivalent to generated markdown content for:
``Workflow Provenance Card: Perceptron GridSearch``.

Summary
~~~~~~~

- **Workflow Name:** ``Perceptron GridSearch``
- **Workflow ID:** ``20c5939f-f3ee-4031-9303-a9e68a5a8092``
- **Campaign ID:** ``661344de-ddf4-497d-a5ba-0d01c67cfb79``
- **Execution Start (UTC):** ``2026-02-19 05:05:10``
- **Execution End (UTC):** ``2026-02-19 05:05:12``
- **Total Elapsed (s):** ``1.501``
- **User:** ``rsr``
- **System Name:** ``Darwin``
- **Environment ID:** ``laptop``
- **Workflow Subtype:** ``ml_workflow``
- **Code Repository:** ``branch=skills, short_sha=f3df676, dirty=dirty``
- **Git Remote:** ``git@github.com:ORNL/flowcept.git``
- **Workflow args:**

  - ``python_random_seeded``: ``True``
  - ``seed``: ``42``
  - ``torch_cuda_manual_seeded``: ``False``
  - ``torch_cudnn_benchmark``: ``False``
  - ``torch_cudnn_deterministic``: ``True``
  - ``torch_deterministic_algorithms``: ``True``
  - ``torch_manual_seeded``: ``True``

Workflow-level Summary
~~~~~~~~~~~~~~~~~~~~~~

- **Total Activities:** ``3``
- **Status Counts:** ``{'FINISHED': 7}``
- **Total Elapsed Workflow Time (s):** ``1.501``

  - ``train_and_validate``: ``0.088 s``
  - ``get_dataset``: ``0.056 s``
  - ``select_best_model``: ``0.041 s``

- **Resource Totals:**

  - ``Memory Used``: ``7.78 MB``
  - ``Average CPU (%)``: ``54.1%``
  - **IO:**

    - ``Read``: ``38.49 MB``
    - ``Write``: ``55.11 MB``
    - ``Read Ops``: ``1,454``
    - ``Write Ops``: ``155``

- **Key Observations:**

  - Slowest Activity: ``train_and_validate`` at ``0.088 s``
  - Largest IO Activity: ``train_and_validate`` with Read ``31.74 MB`` and Write ``52.10 MB``

Workflow Structure
~~~~~~~~~~~~~~~~~~

.. code-block:: text

   input data
           │
           ▼
    get_dataset
           │
    train_and_validate
           │
    select_best_model
           ▼
    output data

Timing Report
~~~~~~~~~~~~~

Rows are sorted by **First Started At** (ascending).

.. list-table::
   :header-rows: 1

   * - Activity
     - Status Counts
     - First Started At
     - Last Ended At
     - Median Elapsed (s)
   * - get_dataset
     - {'FINISHED': 1}
     - 2026-02-19 05:05:10
     - 2026-02-19 05:05:10
     - 0.056
   * - train_and_validate
     - {'FINISHED': 5}
     - 2026-02-19 05:05:10
     - 2026-02-19 05:05:12
     - 0.088
   * - select_best_model
     - {'FINISHED': 1}
     - 2026-02-19 05:05:12
     - 2026-02-19 05:05:12
     - 0.041

Per Activity Details
~~~~~~~~~~~~~~~~~~~~

- **get_dataset** (subtype=``dataprep``)

  - Used:

    - ``n_samples``: ``120``
    - ``split_ratio``: ``0.8``

  - Generated:

    - ``dataset_id``: ``f1e918cc-a3eb-4dd8-8036-5f6e4fc140d1``
    - ``x_train_shape``: ``[96, 2]``
    - ``x_val_shape``: ``[24, 2]``
    - ``y_train_shape``: ``[96, 1]``
    - ``y_val_shape``: ``[24, 1]``

- **train_and_validate** (``n=5``, subtype=``learning``)

  - Used (aggregated): includes ``epochs``, ``learning_rate``, ``n_input_neurons``, ``config_id``, and other fields.
  - Generated (aggregated): includes ``best_val_loss``, ``val_loss``, ``val_accuracy``, and model object ids.

- **select_best_model** (subtype=``model_selection``)

  - Generated:

    - ``selected_config_id``: ``cfg_5``
    - ``selected_loss``: ``0.0490574836730957``
    - ``selected_model_object_id``: ``ae18a739-1ffe-45a8-ae64-827a079579a6``

Workflow-level Resource Usage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Metric
     - Value
   * - Telemetry Samples (task start/end pairs)
     - 7
   * - CPU User Time Delta
     - 7.380
   * - CPU System Time Delta
     - 1.940
   * - Average CPU (%) Delta
     - 54.1%
   * - Average CPU Frequency
     - 3,228
   * - Memory Used Delta
     - 7.78 MB
   * - Average Memory (%)
     - 73.7%
   * - Average Swap (%)
     - 90.0%
   * - Disk Read Time Delta (ms)
     - 224.000
   * - Disk Write Time Delta (ms)
     - 14.000
   * - Disk Busy Time Delta (ms)
     - 0.000

Object Artifacts Summary
~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1

   * - Metric
     - Value
   * - Total Objects
     - 6
   * - By Type
     - {'dataset': 1, 'ml_model': 5}
   * - By Storage
     - {'in_object': 1, 'gridfs': 5}
   * - Task-linked Objects
     - 6
   * - Workflow-linked Objects
     - 6
   * - Max Version
     - 7
   * - Total Size
     - 13.66 KB
   * - Average Size
     - 2.28 KB
   * - Max Size
     - 4.10 KB

Object Details by Type
~~~~~~~~~~~~~~~~~~~~~~

- **Datasets**

  - ``f1e918cc-a3eb-4dd8-8036-5f6e4fc140d1``

    - version: ``0``
    - storage: ``in_object``
    - size: ``4.10 KB``
    - task_id: ``1771477510.9383209``
    - workflow_id: ``20c5939f-f3ee-4031-9303-a9e68a5a8092``
    - timestamp: ``2026-02-19 05:05:10``
    - sha256: ``7d7b4be35ea11f66e9a785d1b39cfb8fc31f8fd23020bc74918872ab5855253c``

- **Models**

  - ``ae18a739-1ffe-45a8-ae64-827a079579a6``

    - version: ``7``
    - storage: ``gridfs``
    - size: ``1.91 KB``
    - tags: ``best``
    - custom_metadata includes ``checkpoint_epoch``, ``class``, ``config_id``, ``learning_rate``, ``loss``, and ``model_profile``.

Aggregation Method
~~~~~~~~~~~~~~~~~~

- Grouping key: ``activity_id``.
- Each grouped row may aggregate multiple task records (``n_tasks``).
- Aggregated metrics currently include count/status/timing.

Generator footer example:

- Provenance card generated by Flowcept | GitHub | Version: 0.9.14 on Feb 19, 2026 at 12:05 AM EST


PDF Reports (Optional)
----------------------

PDF reports are intended for executive-friendly rendering and include plots.

.. code-block:: shell

   pip install flowcept[report_pdf]

.. code-block:: python

   from flowcept import Flowcept

   # 1) Generate PDF from workflow_id (DB-backed mode)
   stats = Flowcept.generate_report(
       report_type="provenance_report",
       format="pdf",
       workflow_id="5def1173-d417-420b-a7ed-61ada01772cd",
       output_path="PROVENANCE_REPORT.pdf",
   )
   print(stats["output"])

   # 2) Generate PDF from in-memory records
   Flowcept.generate_report(
       report_type="provenance_report",
       format="pdf",
       records=my_records,
       output_path="PROVENANCE_REPORT_FROM_RECORDS.pdf",
   )

   # 3) Generate PDF from a Flowcept JSONL file
   Flowcept.generate_report(
       report_type="provenance_report",
       format="pdf",
       input_jsonl_path="/tmp/flowcept_buffer.jsonl",
       output_path="PROVENANCE_REPORT_FROM_JSONL.pdf",
   )

PDF report plots include:

- Top slowest activities
- Top fastest activities
- Most resource-demanding activities (IO)
- Telemetry-aware charts when telemetry fields are available
