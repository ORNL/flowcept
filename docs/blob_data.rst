Blob Data
=========

Flowcept focuses on provenance metadata, but it also supports storing and linking binary data
through ``Flowcept.db``.

See also: :doc:`Blob Data Schema <blob_schema>`.

In practice, use this for:

- model checkpoints
- serialized artifacts
- medium/large files you want linked to tasks/workflows in the same physical database.


When To Use Flowcept.db for blob data management
-----------------------

Use ``Flowcept.db`` when you need a durable object record tied to provenance fields such as:

- ``workflow_id``
- ``task_id``
- ``custom_metadata``

For most provenance-only payloads, particularly for scalar-based values or small arrays,
keep the object in ``used``/``generated`` fields instead.


Blob Storage API
----------------

The main object API is:

- ``Flowcept.db.save_or_update_object(...)``
- ``Flowcept.db.get_blob_object(object_id)``
- ``Flowcept.db.get_blob_fingerprint(object_id)`` (metadata-only hash/size fingerprint)
- ``Flowcept.db.blob_objects_equal(object_id_a, object_id_b)`` (fast equality check by fingerprint)
- ``Flowcept.db.blob_object_query(filter)``
- ``Flowcept.db.query(..., collection="objects")``
- ``Flowcept.db.save_or_update_ml_model(...)`` (alias with ``object_type="ml_model"`` preset)
- ``Flowcept.db.get_ml_model(object_id)`` (alias to ``get_blob_object``)
- ``Flowcept.db.ml_model_query(filter)`` (alias to ``blob_object_query``)
- ``Flowcept.db.save_or_update_dataset(...)`` (alias with ``object_type="dataset"`` preset)
- ``Flowcept.db.get_dataset(object_id)`` (alias to ``get_blob_object``)
- ``Flowcept.db.dataset_query(filter)`` (alias to ``blob_object_query``)

Object records are stored in the ``objects`` collection and can include:

- ``object_id`` (primary key)
- ``task_id`` (optional linkage)
- ``workflow_id`` (optional linkage)
- ``object_type`` (optional category label, defined by you)
- ``custom_metadata`` (optional dictionary)
- ``version`` (int, always present; default ``0`` on first save and incremented on each update)

Meaningful ``object_type`` examples:

- ``ml_model``: trained model/checkpoint bytes (also used by ``save_or_update_torch_model``).
- ``dataset``: a frozen sample or preprocessed dataset blob for reproducibility.
- ``artifact``: generic output artifact (report, serialized object, feature cache).
- ``input_file``: source payload used by a task (for example, uploaded binary input).
- ``embedding_index``: vector index or ANN structure saved for retrieval pipelines.

Depending on ``save_data_in_collection``:

- ``True``: raw bytes are stored in ``data`` (in-object storage).
  Use this for small/medium payloads and fast single-document reads.
- ``False`` (default): binary payload is stored out-of-line (GridFS in MongoDB), and only metadata is in
  the document.
  Use this for larger payloads or frequent updates, where GridFS gives cleaner metadata documents and
  avoids inflating the ``objects`` document size.

**save_data_in_collection=False (with GridFS) advantages**


- Keeps object metadata compact in ``objects`` while storing payload bytes separately.
- Better fit for large binary artifacts (models, checkpoints, compressed datasets).
- History-friendly: old versions can keep their own GridFS file references without rewriting large in-doc blobs.

Version control mode (Git-like history)
---------------------------------------

``Flowcept.db.save_or_update_object(..., control_version=True)`` enables append-only version history.

- control_version=False is the default.
- Latest version is always in the ``objects`` collection.
- Previous versions are appended to ``object_history`` collection.
- First insert with ``control_version=True`` starts at ``version=0``.
- Each update increments the latest version and links with ``prev_version``.

.. note::
   ``object_history`` is expected to be append-only. History documents are immutable and should
   never be updated or deleted, similar to Git commit history.

Retrieve specific versions:

- ``Flowcept.db.get_blob_object(object_id)``: latest from ``objects``.
- ``Flowcept.db.get_blob_object(object_id, version=N)``: exact version lookup (latest or history).

List versions metadata only (no blob bytes):

- ``Flowcept.db.get_object_history(object_id)``

See a full model-checkpoint walkthrough:
:doc:`Versioned Single-Layer Perceptron Example <blob_versioned_model_example>`.

See a full single-layer perceptron walkthrough (including dataset persistence):
:doc:`Versioned Single-Layer Perceptron Example <blob_versioned_single_layer_perceptron_example>`.


Simple Example: Store Bytes + Linkage Fields
---------------------------------------------

.. code-block:: python

   from flowcept import Flowcept

   with Flowcept(workflow_name="blob_demo"):
       # Any bytes payload (file bytes, serialized artifact, etc.)
       payload = b"hello-blob"

       obj_id = Flowcept.db.save_or_update_object(
           object=payload,
           task_id="task_demo_001",
           object_type="artifact",
           custom_metadata={"mime_type": "application/octet-stream", "source": "demo"},
           save_data_in_collection=True,  # keep bytes in-object (`data` field)
           control_version=True,
       )

       doc = Flowcept.db.get_blob_object(obj_id)
       assert doc.workflow_id == Flowcept.current_workflow_id
       assert doc.task_id == "task_demo_001"
       assert doc.custom_metadata["source"] == "demo"
       assert doc.version == 0


Simple Example: Update Existing Object Metadata
-----------------------------------------------

.. code-block:: python

   # Reuse object_id to update the same object record
   Flowcept.db.save_or_update_object(
       object=b"hello-blob-v2",
       object_id=obj_id,
       task_id="task_demo_001",
       object_type="artifact",
       custom_metadata={"note": "updated content"},
       save_data_in_collection=True,
       control_version=True,
   )

   # version is now incremented by the DB update
   updated = Flowcept.db.get_blob_object(obj_id)
   assert updated.version == 1


Simple Example: Save Dataset Snapshot (Alias API)
-------------------------------------------------

.. code-block:: python

   with Flowcept(workflow_name="dataset_blob_demo"):
       ds_id = Flowcept.db.save_or_update_dataset(
           object={
               "x_train": x_train,
               "y_train": y_train,
               "x_val": x_val,
               "y_val": y_val,
           },
           task_id="prepare_data_001",
           custom_metadata={"split_ratio": 0.8, "n_samples": 120},
           save_data_in_collection=True,
           pickle=True,
           control_version=True,
       )

       ds_blob = Flowcept.db.get_dataset(ds_id)
       assert ds_blob.object_type == "dataset"
       assert ds_blob.task_id == "prepare_data_001"


PyTorch Model Helpers (Flowcept.db)
-----------------------------------

Flowcept includes model-specific helpers that are used in tests/examples:

- ``Flowcept.db.save_or_update_torch_model(model, ...)``
- ``Flowcept.db.load_torch_model(model, object_id)``

These helpers store/load ``state_dict`` and let you attach provenance linkage fields.

.. code-block:: python

   from torch import nn
   from flowcept import Flowcept

   with Flowcept(workflow_name="torch_blob_demo"):
       wf_id = Flowcept.current_workflow_id
       model = nn.Module()

       model_obj_id = Flowcept.db.save_or_update_torch_model(
           model,
           workflow_id=wf_id,
           task_id="train_task_001",
           custom_metadata={"stage": "best_model", "metric": "val_loss"},
       )

       loaded = nn.Module()
       model_doc = Flowcept.db.load_torch_model(loaded, model_obj_id)
       assert model_doc["workflow_id"] == wf_id
       assert model_doc["task_id"] == "train_task_001"


Notes
-----

- Blob/object persistence is currently implemented in MongoDB-backed mode.
- LMDB DAO does not currently implement object blob persistence methods.
