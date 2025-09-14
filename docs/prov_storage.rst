Provenance Storage
==================

Flowcept uses an ephemeral **message queue (MQ)** with a publish/subscribe (pub-sub) system to flush observed data.  
For optional persistence, you can choose between:

- `LMDB <https://lmdb.readthedocs.io/>`_ (default)  
  A lightweight, file-based database requiring no external services (but may require ``gcc``).  
  Ideal for simple tests or cases needing basic persistence without query capabilities.  
  Data stored in LMDB can be loaded into tools like Pandas for analysis, and Flowcept's Database API can export LMDB data into Pandas DataFrames.

- `MongoDB <https://www.mongodb.com/>`_  
  A robust, service-based database with advanced query support.  
  Required to use Flowcept's Query API (``flowcept.Flowcept.db``) for complex queries and features like ML model management or runtime queries (query while writing).  

Flowcept supports writing to both databases simultaneously (default), individually, or to neither, depending on configuration.
See `setup instructions <https://flowcept.readthedocs.io/en/latest/setup.html#setup>`_.

If persistence is disabled, captured data is sent to the MQ without any default consumer subscribing to it.  
In this case, querying requires writing a custom consumer to subscribe and store the data.  

.. note::

   For querying, the Flowcept Database API uses **only one database at a time**.  
   If both MongoDB and LMDB are enabled, Flowcept defaults to MongoDB.  
   If neither is enabled, an error occurs.  
   Data stored in MongoDB and LMDB are interchangeable and can be transferred between them.

Saving the In-Memory Buffer to Disk
-----------------------------------

Flowcept can persist the in-memory message buffer to a **JSON Lines (JSONL)** file in both **offline** and **online** modes. This is useful for audits, simple centralized runs, and quick ad‑hoc analysis.

Configuration
^^^^^^^^^^^^^

Default dumping is enabled and writes to ``flowcept_buffer.jsonl``:

To favor local files (**offline**), set:

.. code-block:: yaml

   project:
     db_flush_mode: offline   # keeps messages local (no DB writes)
     dump_buffer:
       enabled: true
       path: flowcept_buffer.jsonl

For standard **online** runs (DB writes enabled) while still keeping a file copy:

.. code-block:: yaml

   project:
     db_flush_mode: online    # default
     dump_buffer:
       enabled: true
       path: flowcept_buffer.jsonl

Usage
^^^^^

Dump the buffer (during or at the end of a run):

.. code-block:: python

   from flowcept import Flowcept

   with Flowcept(workflow_name="demo") as f:
       # ... your tasks ...
       f.dump_buffer()                   # uses settings path
       f.dump_buffer("my_buffer.jsonl") # custom path


Read the buffer file later (as list or DataFrame):

.. code-block:: python

   from flowcept import Flowcept

   # 1) List of dicts
   msgs = Flowcept.read_buffer_file("flowcept_buffer.jsonl")

   # 2) DataFrame without flattening (nested dicts stay as objects)
   df_raw = Flowcept.read_buffer_file("flowcept_buffer.jsonl", return_df=True, normalize_df=False)

   # 3) DataFrame with dotted columns (normalized)
   df_norm = Flowcept.read_buffer_file("flowcept_buffer.jsonl", return_df=True, normalize_df=True)


Delete a buffer file if needed:

.. code-block:: python

   from flowcept import Flowcept
   Flowcept.delete_buffer_file()                  # deletes default path from settings
   Flowcept.delete_buffer_file("my_buffer.jsonl")


.. note::

   The file-based method is **best suited for offline mode** or small, centralized runs.
   Each ``interceptor`` in a Flowcept instance maintains its own in-memory buffer.
   In distributed settings (e.g., HPC jobs or distributed workflows), this creates separate buffer
   files per interceptor. To run an end-to-end analysis, you must manually merge all files.

   For distributed runs, prefer the **MongoDB** provenance storage option, which consolidates all
   captured provenance into a single database automatically.
   Alternatively, implement a **custom consumer** to centralize message ingestion and
   enable real-time analysis.

See also
^^^^^^^^

- `Buffer querying <https://flowcept.readthedocs.io/en/latest/prov_query.html#accessing-the-in-memory-buffer>`_
- `Implementing a custom consumer <https://flowcept.readthedocs.io/en/latest/prov_storage.html#example-extending-the-base-consumer>`_
- `Flowcept API Reference <https://flowcept.readthedocs.io/en/latest/api-reference.html#main-flowcept-object>`_

---

Provenance Consumer
===================

Flowcept relies on consumers to subscribe to the MQ and persist messages into databases.  
The consumer interface is defined by the :class:`BaseConsumer`, which provides a standard lifecycle for message handling:

- Subscribe to the MQ.  
- Listen for messages.  
- Dispatch each message to a ``message_handler`` method.  
- Decide whether to continue listening or stop based on the handler's return value.  

Developers can subclass :class:`BaseConsumer` to implement custom provenance consumers.

Example: Extending the Base Consumer
------------------------------------

Below is a simple consumer implementation that listens for messages of type ``task``, converts them into :class:`TaskObject`, and prints selected fields.  
This can serve as a template for building custom provenance consumers.

.. code-block:: python

   from typing import Dict

   from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
   from flowcept.flowceptor.consumers.base_consumer import BaseConsumer


   class MyConsumer(BaseConsumer):

       def __init__(self):
           super().__init__()

       def message_handler(self, msg_obj: Dict) -> bool:
           if msg_obj.get("type", "") == "task":
               msg = TaskObject.from_dict(msg_obj)
               print(msg)
               if msg.used:
                   print(f"\t\tUsed: {msg.used}")
               if msg.generated:
                   print(f"\t\tGenerated: {msg.generated}")
               if msg.custom_metadata:
                   print(f"\t\tCustom Metadata: {msg.custom_metadata}")

               print()
               print()
           else:
               print(f"We got a msg with different type: {msg_obj.get('type', None)}")
           return True


   if __name__ == "__main__":

       print("Starting consumer indefinitely. Press ctrl+c to stop")
       consumer = MyConsumer()
       consumer.start(daemon=False)


**Notes**:

- See also: `Explicit publish example <file:///Users/rsr/Documents/GDrive/ORNL/dev/flowcept/docs/_build/html/prov_capture.html#custom-task-creation-fully-customizable>`_
- See also: `Ping pong example via PubSub with Flowcept <https://github.com/ORNL/flowcept/blob/main/examples/consumers/ping_pong_example.py>`_



Document Inserter
-----------------

The :class:`DocumentInserter` is the main consumer. It processes task and workflow messages, adds metadata or telemetry summaries, sanitizes fields, and persists them into configured databases (MongoDB, LMDB, or both).

Key responsibilities:

- **Buffering:** Uses an autoflush buffer to batch inserts, reducing overhead. Flushes can be triggered by size or time interval.  
- **Task handling:** Enriches task messages with telemetry summaries and critical task tags, generates IDs if missing, and ensures status consistency.  
- **Workflow handling:** Converts workflow messages into :class:`WorkflowObject` instances and persists them.  
- **Control handling:** Responds to control messages (e.g., safe stop signals).  

The consumer runs in its own thread (or synchronously, if configured) and ensures reliable, structured persistence of provenance data.

Extensibility
-------------

Developers can build new consumers by subclassing :class:`BaseConsumer`.  
For example, one could implement consumers that persist provenance into **graph databases** (e.g., Neo4j) or **relational databases** (e.g., PostgreSQL), using the same message-handling loop.

The :class:`DocumentInserter` serves as a reference implementation of how to transform and persist messages efficiently while integrating seamlessly with Flowcept's MQ-based architecture.
