# Flowcept LLM Tutorial: Progressive Provenance Capture

This tutorial shows how to capture provenance in **Flowcept** step by step, increasing detail from a simple campaign-level run to subworkflows, PyTorch model forwards, and loop instrumentation. You will see how the same training code yields richer provenance as you turn on different capture methods.

> Code location: <https://github.com/ORNL/flowcept/tree/main/examples/llm_tutorial>

---

## Scripts at a glance

| Script | Role | Key elements | Imported by |
|---|---|---|---|
| [`llm_train_campaign.py`](llm_train_campaign.py) | Orchestrates a hyperparameter campaign. Runs training jobs (optionally in parallel with Dask). Wires campaign/workflow IDs into runs. | `generate_configs`, `search_workflow`, `main` (argparse), Flowcept context management | Entry point |
| [`llm_dataprep.py`](llm_dataprep.py) | Prepares the dataset (e.g., **WikiText-2**), tokenization, and splits. Emits a **Data Prep Workflow** when Flowcept is enabled. | `dataprep_workflow` | `llm_train_campaign.py` |
| [`llm_model.py`](llm_model.py) | Defines the `TransformerModel`, the training and evaluation loops, and optional Flowcept **Torch instrumentation** (model forwards, per-epoch, per-batch). | `model_train`, `train_epoch`, `evaluate`, `@flowcept_torch`, `FlowceptEpochLoop` | `llm_train_campaign.py` |
| `analysis.ipynb` | Example notebook to inspect provenance from saved JSONL buffer. | Reads JSONL via `Flowcept.read_messages_file(return_df=True)`; sample pandas queries | Standalone |


---

## Quick intro

We run an LLM-style small (able to train on desktop's CPU) training on **WikiText-2**, then progressively enable provenance features in Flowcept. Start with a minimal Dask-driven search workflow, add a Data Prep workflow, then turn on per-epoch loop capture, parent model forwards, child layer forwards, and telemetry. You learn how **campaign → workflow → task** relationships look in the captured data.

### Campaign Workflow Structure

- **Campaign**
  - **Workflow:** Data Prep
  - **Workflow:** Search
    - **Subworkflow:** Module Layer Forward Train
    - **Subworkflow:** Module Layer Forward Test
- **Task:** `model_train` (Dask)
  - **Task:** Loop Iteration x N
    - Parent module forwards - Train
    - Parent module forwards - Test
---

## Requirements

- Python **3.10+**
- **Flowcept** with ML extras and Dask:  
  ```bash
  pip install "flowcept[ml_dev,extras,dask]"
  ```

We expect familiarity with basic Flowcept concepts and with deep learning training basics.

---

## Setup

```bash
git clone https://github.com/ORNL/flowcept.git
cd flowcept/examples/llm_tutorial
conda activate flowpcept # or use venv
pip install "flowcept[ml_dev,extras,dask]"
# You may need to adjust PyTorch packages per your platform (see pytorch.org)
flowcept --init-settings
```

Adjust your generated **settings.yaml** file as you move through the stages below. Initial settings:

```yaml
project:
  enrich_messages: true # Add extra metadata to task messages, such as IP addresses of the node that executed the task, UTC timestamps, GitHub repo metadata.
  db_flush_mode: offline # Mode for flushing DB entries: "online" or "offline". If online, flushes to the DB will happen before the workflow ends.
  dump_buffer: # This is particularly useful if you need to run completely offline. If you omit this, even offline, buffer data will not be persisted.
    enabled: true
    path: flowcept_buffer.jsonl

instrumentation:
  enabled: false
  torch:
    what: ~                  # parent_only | parent_and_children | ~
    children_mode: ~         # tensor_inspection | telemetry | telemetry_and_tensor_inspection
    epoch_loop: ~            # default | lightweight | ~
    batch_loop: ~            # default | lightweight | ~
    capture_epochs_at_every: 1
    register_workflow: false

telemetry_capture: ~         #  control telemetry capture
```

---

## How to run

1. Adjust `settings.yaml` for the desired capture level.
2. Run the campaign entry point:
   ```bash
   python llm_train_campaign.py
   ```
3. Inspect the captured data:
   
 ```python
 from flowcept import Flowcept
 df = Flowcept.read_messages_file("flowcept_messages.jsonl", return_df=True)
 print(df.shape, list(df.columns)[:12])
  ```

Inspect the workflow row.

---

## Progressive capture levels

Each step below modifies `settings.yaml` minimally, so you can see how much additional provenance arrives.

### 1) Search Workflow only

- Set:
  ```yaml
  instrumentation:
    enabled: false
  ```
- What runs: the Dask `model_train` task for one hyperparameter combination.
- Expect roughly **3 rows** in JSONL: two for the Dask task (init and end) and one workflow record.

### 2) Add the Data Prep workflow

- Enable instrumentation but keep Torch off:
  ```yaml
  project:
    enrich_messages: false # let's disable it for now, for clarity. We'll re-enable later.
  instrumentation:
    enabled: true
    torch:
      what: ~
      children_mode: ~
      epoch_loop: ~
      batch_loop: ~
      capture_epochs_at_every: 1
      register_workflow: false
  ```
- `llm_dataprep.py` contributes a **Data Prep Workflow**.
- Expect roughly **4 rows** total.

### 3) Per-epoch instrumentation

- Turn on epoch loop capture:
  ```yaml
  instrumentation:
    enabled: true
    torch:
      what: ~
      children_mode: ~
      epoch_loop: default
      batch_loop: ~
      capture_epochs_at_every: 1
      register_workflow: false
  ```
- Default epochs in the example are **4**.  
- Expect **8 rows** total (adds one per epoch).

### 4) Parent model forwards (no inner layers)

- Capture only the top-level model call (`model(data)`):
  ```yaml
  instrumentation:
    enabled: true
    torch:
      what: parent_only
      children_mode: ~
      epoch_loop: default
      batch_loop: ~
      capture_epochs_at_every: 4    # capture at a single epoch for clarity
      register_workflow: false
  ```
- With the default small dataset, you will see **2 train** and **4 eval** forwards at the captured epoch.  
- Expect **14 rows** total.

### 5) Register the model definition as a workflow

- Same as (4) but set:
  ```yaml
  instrumentation:
    enabled: true
    torch:
      what: parent_only
      children_mode: ~
      epoch_loop: default
      batch_loop: ~
      capture_epochs_at_every: 4
      register_workflow: true
  ```
- Adds a workflow row for the model (e.g., `TransformerModel`) that points to the search workflow.
- Expect  **15 rows** total.

### 6) Capture forwards for every layer and every epoch

- Capture all inner layers and every epoch:
  ```yaml
  instrumentation:
    enabled: true
    torch:
      what: parent_and_children
      children_mode: tensor_inspection   # or telemetry / telemetry_and_tensor_inspection
      epoch_loop: default
      batch_loop: ~
      capture_epochs_at_every: 1
      register_workflow: true
  ```
- There are **4 epochs**, with **2 train** and **4 eval** forwards per epoch at the parent level, plus child forwards.  
- Expect **33 rows** total for the parent-level events as described above; child-level events further increase detail depending on your `children_mode`.

### 7) Enabling telemetry and message enrichment

- Add host-level telemetry and extra metadata:
  ```yaml
  project:
    enrich_messages: true

  telemetry_capture:
    cpu: true

  instrumentation:
    enabled: true
    torch:
      what: parent_only
      epoch_loop: default
      batch_loop: ~
      capture_epochs_at_every: 1
      register_workflow: true
  ```

---

## Tips

- Use `python llm_train_campaign.py --help` to see runtime flags.
- In `analysis.ipynb`, start with `Flowcept.read_messages_file(..., return_df=True)` and filter on columns like `name`, `type`, `subtype`, `parent_task_id`, `workflow_id`, and `campaign_id`.

