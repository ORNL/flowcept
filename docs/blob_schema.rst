Blob Object Schema
==================

Flowcept stores binary payload metadata in the ``objects`` collection.
The public metadata object is represented by :class:`flowcept.commons.flowcept_dataclasses.blob_object.BlobObject`.

Core Fields
-----------

- **object_id** (str): Unique identifier for the stored object.
- **version** (int): Monotonic object version. It starts at ``0`` and increments on updates.

Linkage Fields
--------------

- **task_id** (str): Task associated with this object, when applicable.
- **workflow_id** (str): Workflow associated with this object, when applicable.

Metadata Fields
---------------

- **object_type** (str): User-defined category label for the object, such as ``ml_model``, ``dataset``, ``artifact``, or ``input_file``.
- **custom_metadata** (dict): Free-form user metadata.
- **tags** (list[str]): Optional labels associated with the object.

Storage Fields
--------------

The DAO may add storage-specific fields to documents in ``objects`` or ``object_history``. Common examples include:

- **object_size_bytes** (int): Payload size in bytes, when available.
- **data_sha256** (str): SHA-256 payload hash, when available.
- **data_hash_algo** (str): Hash algorithm label.
- **grid_fs_file_id**: GridFS pointer when payload bytes are stored out-of-line.
- **data**: In-document payload bytes when ``save_data_in_collection`` is enabled.

Notes
-----

- ``object_type`` is the semantic object category. Do not use ``type`` for this purpose.
- ``BlobObject.to_dict()`` emits non-null metadata fields and always includes ``version``.
- In version-control mode, Flowcept stores the latest object in ``objects`` and older versions in ``object_history``.
