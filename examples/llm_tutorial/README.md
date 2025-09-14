# Complex end-to-end Example on a LLM Training Workflow

This illustrative example shows an LLM training workflow by fine-tuning hyperparameter (aka hyperparameter search) over Wikidata.
It is similar to a parallel grid search using Dask to run the parallel model training.

This is composed of two main workflows: Data Preparation and Model Search workflow

## Requirements

`pip install flowcept[ml_dev,extras]`  # You can need to add nvidia/AMD GPU telemetry capture.

# Campaign > Workflow > Task structure

    Campaign:
        Data Prep Workflow
        Search Workflow

    Workflows:
        Data Prep Workflow
        Search workflow ->
          Module Layer Forward Train Workflow
          Module Layer Forward Test Workflow

    Tasks:
        Main workflow . Main model_train task (dask task) ->
            Main workflow . Epochs Whole Loop
                Main workflow . Loop Iteration Task
                    Module Layer Forward Train Workflow . Parent module forward tasks

            Module Layer Forward Test Workflow . Parent module forward tasks

## Growing in complexity

Run the [llm_train_campaign.py](llm_train_campaign.py) script by incrementally growing the complexity of the provenance capture by adjusting the settings file.

#### Disable telemetry

Adjust the `settings.yaml`:
```yaml
telemetry_capture: ~  # Remember, ~ is the same as null. This will disable telemetry.
```

# 1. Search Workflow only

See the function `search_workflow` [here](llm_train_campaign.py). For each combination of hyperparameters, it will run the function `model_train` from [llm_model.py](llm_model.py) in parallel.

Adjust the `settings.yaml`:
```yaml
instrumentation:
  enabled: false
``` 

**Expected outcome:**

`Flowcept.read_buffer_file(return_df=True)` should return 3 rows: two for the dask (`model_train`) tasks (init and end messages) and one for the workflow object.

**Reason:** Here, we are running only with the Dask plugins. The default args of the [llm_train_campaign.py](llm_train_campaign.py) in this tutorial only runs one dask task (i.e., it evaluates only one combination of hyperparameters).  All other instrumentation is disabled. This is the level of granularity of most provenance systems.

## 2. Adding the Data Prep workflow.

See the `with Flowcept` block inside the [llm_dataprep.py](llm_dataprep.py).

Adjust the `settings.yaml`:
```yaml
instrumentation:
  enabled: true # This toggles data capture for instrumentation.
  torch:
    what: ~ # Scope of instrumentation: "parent_only" -- will capture only at the main model level, "parent_and_children" -- will capture the inner layers, or ~ (disable).
    children_mode: ~   # What to capture if parent_and_children is chosen in the scope. Possible values: "tensor_inspection" (i.e., tensor metadata), "telemetry", "telemetry_and_tensor_inspection"
    epoch_loop: ~ # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    batch_loop: ~ # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    capture_epochs_at_every: 1 # Will capture data at every N epochs; please use a value that is multiple of the total number of #epochs.
    register_workflow: false
```

**Expected outcome:**

`Flowcept.read_buffer_file(return_df=True)` should return 4 rows: same as before + the data prep workflow.

**Reason:** By enabling the instrumentation but keeping all other PyTorch-related instrumentation disabled, only the Data Prep workflow is added to the buffer.


## 3. Add Per-epoch Instrumentation

See `FlowceptEpochLoop` usage in [llm_model.py](llm_model.py). 

Adjust the `settings.yaml`:
```yaml
instrumentation:
  enabled: true # This toggles data capture for instrumentation.
  torch:
    what: ~ # Scope of instrumentation: "parent_only" -- will capture only at the main model level, "parent_and_children" -- will capture the inner layers, or ~ (disable).
    children_mode: ~   # What to capture if parent_and_children is chosen in the scope. Possible values: "tensor_inspection" (i.e., tensor metadata), "telemetry", "telemetry_and_tensor_inspection"
    epoch_loop: default # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    batch_loop: ~ # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    capture_epochs_at_every: 1 # Will capture data at every N epochs; please use a value that is multiple of the total number of #epochs.
    register_workflow: false # Will store the parent model forward as a workflow itself in the database.
``` 

**Expected outcome:**

`Flowcept.read_buffer_file(return_df=True)` should return 8 rows: 4 as before plus 4 new rows, one per each epoch.

**Reason:** The default arguments of [llm_train_campaign.py](llm_train_campaign.py) uses 4 epochs.
Notice that every epoch iteration task has a `parent_task_id` that should point to the Dask task (the `model_train` task).

## 4. Adding PyTorch Model Forwards

If this is enabled, whenever a PyTorch model is invoked (e.g., whenever there is a call like `model(data)`, model prov. will be captured)

See the `TransformerModel` class definition, especially the `@flowcept_torch` decorator, and see its instantiation in the file [llm_model.py](llm_model.py). In the instantiation, notice the arguments:
```python    
parent_workflow_id=workflow_id,
campaign_id=campaign_id,
get_profile=True,
capture_enabled=with_flowcept
```

Adjust the `settings.yaml`:
```yaml
instrumentation:
  enabled: true # This toggles data capture for instrumentation.
  torch:
    what: parent_only # Scope of instrumentation: "parent_only" -- will capture only at the main model level, "parent_and_children" -- will capture the inner layers, or ~ (disable).
    children_mode: ~   # What to capture if parent_and_children is chosen in the scope. Possible values: "tensor_inspection" (i.e., tensor metadata), "telemetry", "telemetry_and_tensor_inspection"
    epoch_loop: default # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    batch_loop: ~ # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    capture_epochs_at_every: 4 # Will capture data at every N epochs; please use a value that is multiple of the total number of #epochs.
    register_workflow: false # Will store the parent model forward as a workflow itself in the database.
```

Setting `parent_only` capture means that only the high-level model pass will be captured. The inner layers (aka children modules) will not be captured. 
Also, notice that we `set capture_epochs_at_every: 4`  because we know that the default setting has 4 epochs. This is just for didactic purposes, to only capture provenance at one epoch (out of the 4). 

**Expected outcome:**

`Flowcept.read_buffer_file(return_df=True)` should return 14 rows: 8 as before plus 6 new ones. 

**Explanation:** Because of the default settings for train and eval batch sizes, and the default setting limits the number of samples in the input dataset to use, the number train batches is `2` and the number of test batches is `4`.
In every batch, there will be a model pass.
See the `model(data)` calls inside the functions `train_epoch` and `evaluate` in the [llm_model.py](llm_model.py) file.

In each new row, observe the fields `used`, `generated`,  `custom_metadata`, `parent_task_id`, `subtype

## 5. Saving the Model definition as a Flowcept workflow

This enables storing high-level metadata about the model.

Adjust the `settings.yaml`:
```yaml
instrumentation:
  enabled: true # This toggles data capture for instrumentation.
  torch:
    what: parent_only # Scope of instrumentation: "parent_only" -- will capture only at the main model level, "parent_and_children" -- will capture the inner layers, or ~ (disable).
    children_mode: ~   # What to capture if parent_and_children is chosen in the scope. Possible values: "tensor_inspection" (i.e., tensor metadata), "telemetry", "telemetry_and_tensor_inspection"
    epoch_loop: default # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    batch_loop: ~ # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    capture_epochs_at_every: 4 # Will capture data at every N epochs; please use a value that is multiple of the total number of #epochs.
    register_workflow: true # Will store the parent model forward as a workflow itself in the database.
```

**Expected outcome:**

`Flowcept.read_buffer_file(return_df=True)`  should return 15 rows: 14 as before plus a new workflow row (`df[df.name == 'TransformerModel']`). Inspect it, particularly the fields `custom_metadata`, `parent_workflow_id` (which should point to the `SearchWorkflow` workflow).

## 6. Adding PyTorch Model Forwards for Every Layer

Adjust the `settings.yaml`:
```yaml
instrumentation:
  enabled: true # This toggles data capture for instrumentation.
  torch:
    what: parent_only # Scope of instrumentation: "parent_only" -- will capture only at the main model level, "parent_and_children" -- will capture the inner layers, or ~ (disable).
    children_mode: ~   # What to capture if parent_and_children is chosen in the scope. Possible values: "tensor_inspection" (i.e., tensor metadata), "telemetry", "telemetry_and_tensor_inspection"
    epoch_loop: default # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    batch_loop: ~ # lightweight, ~ (disable), or default (default will use the default telemetry capture method)
    capture_epochs_at_every: 1 # Will capture data at every N epochs; please use a value that is multiple of the total number of #epochs.
    register_workflow: true # Will store the parent model forward as a workflow itself in the database.
```

**Expected outcome:**

`Flowcept.read_buffer_file(return_df=True)`  should return 33 rows: 15 as before + 6*3.

**Explanation:** Explanation: We capture model forwards for every epoch. There are 4 epochs. Each epoch has 2 train forwards and 4 eval forwards, so 6 forwards per epoch. We previously captured one epoch (6 forwards). Now we capture all four, adding 18 rows and reaching 33 total.


