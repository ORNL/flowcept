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
  To use MongoDB, start the service with ``make services-mongo``.

Flowcept supports writing to both databases simultaneously (default), individually, or to neither, depending on configuration.

If persistence is disabled, captured data is sent to the MQ without any default consumer subscribing to it.  
In this case, querying requires writing a custom consumer to subscribe and store the data.  

.. note::

   For querying, the Flowcept Database API uses **only one database at a time**.  
   If both MongoDB and LMDB are enabled, Flowcept defaults to MongoDB.  
   If neither is enabled, an error occurs.  
   Data stored in MongoDB and LMDB are interchangeable and can be transferred between them.

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
