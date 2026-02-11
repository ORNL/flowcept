Provenance Querying
====================

Flowcept captures detailed provenance about workflows, tasks, agents, and data artifacts (e.g., ML models). Once captured, there are multiple ways to query this provenance depending on your needs. This guide summarizes the main mechanisms available for querying Flowcept data.

.. note::

    Persistence is optional in Flowcept. You can configure Flowcept to use LMDB, MongoDB or both. For more complex queries, we recommend using it with Mongo. The in-memory buffer data is also available with a list of raw JSON data, which can also be queried. See also: `provenance storage <https://flowcept.readthedocs.io/en/latest/prov_storage.html>`_.


Querying with the Command‑Line Interface
----------------------------------------

Flowcept provides a small CLI for quick database queries. The CLI requires MongoDB to be enabled. After installing Flowcept, you will be able to run queries from the CLI.  The usage pattern is:

.. code-block:: console

    flowcept --<function-name-with-dashes> [--<arg-name-with-dashes>=<value>]

Important query‑oriented commands include:

* ``workflow-count`` – count tasks, workflows and objects for a given workflow ID.
* ``query`` – run a MongoDB query against the tasks collection, with optional projection, sorting and limit.
* ``get-task`` – fetch a single task document by its ID.

Here’s an example session:

.. code-block:: console

    # count the number of tasks, workflows and objects for a workflow
    flowcept --workflow-count --workflow-id=123e4567-e89b-12d3-a456-426614174000

    # query tasks where status is COMPLETED and only return `activity_id` and `status`
    flowcept --query --filter='{"status": "COMPLETED"}' \
            --project='{"activity_id": 1, "status": 1, "_id": 0}' \
            --sort='[["started_at", -1]]' --limit=10

    # fetch a task by ID
    flowcept --get-task --task-id=24aa4e52-9aec-4ef6-8cb7-cbd7c72d436e

The CLI prints JSON results to stdout. For full usage details see the official CLI reference.

Querying via the Python API (`Flowcept.db`)
-------------------------------------------

For programmatic access inside scripts and notebooks, Flowcept exposes a database API via the ``Flowcept.db`` property. When MongoDB is enabled this property returns an instance of the internal `DBAPI` class. You can call any of the following methods:

* ``task_query(filter, projection=None, limit=0, sort=None)`` – query the `tasks` collection with an optional projection, sort and limit.
* ``workflow_query(filter)`` – query the `workflows` collection.
* ``get_workflow_object(workflow_id)`` – fetch a workflow and return a `WorkflowObject`.
* ``insert_or_update_task(task_object)`` – insert or update a task.
* ``save_or_update_object(object, type, custom_metadata, …)`` – persist binary objects such as models or large artifacts.

Below is a typical usage pattern:

.. code-block:: python

    from flowcept import Flowcept

    # query tasks for the current workflow
    tasks = Flowcept.db.get_tasks_from_current_workflow()
    print(f"Tasks captured in current workflow: {len(tasks)}")

    # find all tasks marked with a "math" tag
    math_tasks = Flowcept.db.task_query(filter={"tags": "math"})
    for t in math_tasks:
        print(f"{t['task_id']} – {t['activity_id']}: {t['status']}")

    # fetch a workflow object and inspect its arguments
    wf = Flowcept.db.get_workflow_object(workflow_id="123e4567-e89b-12d3-a456-426614174000")
    print(wf.workflow_args)

The `DBAPI` exposes many other methods, such as `get_tasks_recursive` to retrieve all descendants of a task, or `dump_tasks_to_file_recursive` to export tasks to Parquet. See the API reference for details.

Accessing the in-memory buffer
------------------------------

Flowcept keeps recently captured messages in memory as a list of dictionaries. This is handy for debugging and lightweight scripts. In online mode the buffer may be flushed to the MQ periodically.

.. code-block:: python

   from flowcept import Flowcept

   with Flowcept(workflow_name="demo") as f:
       # ... run your tasks ...
       raw_list = f.get_buffer()                 # list[dict]
       df = f.get_buffer(return_df=True)         # pandas.DataFrame with dotted columns
       assert "generated.attention" in df.columns

Dumping the buffer to disk (online or offline)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can persist the buffer to a JSON Lines file in both offline and online runs.

.. code-block:: python

   with Flowcept(workflow_name="demo") as f:
       # ... run your tasks ...
       f.dump_buffer()                  # uses settings path (see below)
       f.dump_buffer("my_buffer.jsonl") # custom path

Default configuration enables dumping to ``flowcept_buffer.jsonl``:

- ``"project": {"dump_buffer": {"enabled": True, "path": "flowcept_buffer.jsonl"}}``

You can control DB flushing and the buffer path in your settings:

.. code-block:: yaml

   project:
     db_flush_mode: online   # "online" or "offline"
     dump_buffer:
       enabled: true
       path: flowcept_buffer.jsonl
       append_workflow_id_to_path: false
       append_id_to_path: false
       delete_previous_file: true

- **Offline mode**: set ``project.db_flush_mode: offline`` to keep messages local.
- **Online mode**: keep ``online``; you can still dump and read the file at any time.
- **append_workflow_id_to_path**: when true, Flowcept writes ``flowcept_buffer_<workflow_id>.jsonl`` (before the extension).
- **append_id_to_path**: when true, Flowcept appends a unique ID to reduce collisions for parallel writers (for example, ``flowcept_buffer_<workflow_id>_<id>.jsonl``).
- **delete_previous_file**: when true, Flowcept deletes the existing buffer file at startup (before a new run).

Reading a buffer file (list or DataFrame)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Use :meth:`Flowcept.read_buffer_file` to load a buffer file later. If no file path is provided, the one configured in the settings.yaml will be used.

.. code-block:: python

   from flowcept import Flowcept

   # 1) List of dicts
   msgs = Flowcept.read_buffer_file("flowcept_buffer.jsonl")
   print(f"Loaded {len(msgs)} messages")

   # 2) DataFrame without flattening (nested dicts stay as objects)
   df_raw = Flowcept.read_buffer_file("flowcept_buffer.jsonl", return_df=True, normalize_df=False)

   # 3) DataFrame with dotted columns (normalized)
   df_norm = Flowcept.read_buffer_file("flowcept_buffer.jsonl", return_df=True, normalize_df=True)
   assert "generated.attention" in df_norm.columns

Consolidating multiple buffer files
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When ``append_workflow_id_to_path`` and ``append_id_to_path`` are enabled, parallel runs can produce multiple JSONL
files for the same workflow. Use ``consolidate=True`` to merge them before reading. This mode:

- Requires ``workflow_id``; it is used to match file names.
- Writes a consolidated file named ``<base>_<workflow_id>.jsonl`` (based on the base path).
- Optionally deletes the split files when ``cleanup_files=True`` (default).
- Returns the consolidated file path; if only a consolidated file exists, nothing is deleted and it is read directly.

.. code-block:: python

   from flowcept import Flowcept

   msgs = Flowcept.read_buffer_file(
       file_path="flowcept_buffer.jsonl",
       consolidate=True,
       workflow_id="your-workflow-id",
   )
   print(f"Loaded {len(msgs)} messages")

By default, ``cleanup_files=True`` removes the intermediate files and keeps a single consolidated
``flowcept_buffer_<workflow_id>.jsonl`` file.

.. note::
   If you used ``append_id_to_path``, pass the same base ``file_path`` used in settings (the ``path`` value in
   ``project.dump_buffer``), not one of the split file names. The consolidator looks for files that match the base
   name pattern ``<base>_<workflow_id>*``. When ``consolidate=True``, you must also pass ``workflow_id``.

Deleting a buffer file
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   from flowcept import Flowcept
   Flowcept.delete_buffer_file()                     # deletes default path from settings
   Flowcept.delete_buffer_file("my_buffer.jsonl")

Notes
^^^^^

- DataFrame returns require ``pandas``. If you installed Flowcept with optional extras, ``pandas`` is included.
- Binary payloads, when present, are stored under the ``data`` key in the buffer messages. However, they are not stored in the buffer file.
- See also: `persisting the in-memory buffer. <https://flowcept.readthedocs.io/en/latest/prov_storage.html#saving-the-in-memory-buffer-to-disk>`_

Working Directly with MongoDB
-----------------------------

If MongoDB is enabled in your settings you may prefer to query the database directly, especially for complex aggregation pipelines. Flowcept stores tasks in the ``tasks`` collection, workflows in ``workflows``, and binary objects in ``objects``. You can use any MongoDB tool or client library, such as:

* **PyMongo** – Python driver for MongoDB; perfect for custom scripts.
* **MongoDB Compass** – graphical UI for ad‑hoc queries and visualisation.
* **mongo shell** or **mongosh** – CLI for interactive queries.

For example, using PyMongo:

.. code-block:: python

    import pymongo

    client = pymongo.MongoClient("mongodb://localhost:27017")
    db = client["flowcept"]
    # find the 20 most recent tasks for a workflow
    tasks = db.tasks.find(
        {"workflow_id": "123e4567-e89b-12d3-a456-426614174000"},
        {"_id": 0, "activity_id": 1, "status": 1}
    ).sort("started_at", pymongo.DESCENDING).limit(20)
    for t in tasks:
        print(t)

The connection string, database name and authentication credentials are configured in the Flowcept settings file.

Working with LMDB
-----------------

If LMDB is enabled instead of MongoDB Flowcept stores data in a directory (default: ``flowcept_lmdb``). LMDB is a file‑based key–value store; it does not support ad‑hoc queries out of the box, but you can read the data programmatically. Flowcept’s `DBAPI` can export LMDB data into pandas DataFrames, allowing you to analyse offline runs without MongoDB:

.. code-block:: python

    from flowcept import Flowcept

    # export LMDB tasks to a DataFrame
    df = Flowcept.db.to_df(collection="tasks")
    print(df.head())

Alternatively, you can use the `lmdb` Python library to iterate over raw key–value pairs. The LMDB environment is located under the directory configured in your settings file (commonly named ``flowcept_lmdb``). Because LMDB stores binary values, you’ll need to serialise and deserialise JSON messages yourself.

Monitoring Provenance with Grafana
----------------------------------

Flowcept supports streaming provenance into monitoring dashboards. A sample Docker compose file (`deployment/compose-grafana.yml`) runs Grafana along with MongoDB and Redis. Grafana is configured with a pre‑built MongoDB‑Grafana image and exposes a port (3000) for the dashboard. To configure Grafana to query Flowcept’s MongoDB, create a new data source with the URL `mongodb://flowcept_mongo:27017` and specify the database name (usually `flowcept`). The compose file sets environment variables for the admin user and password so you can log in and create your own panels.

Grafana can also connect directly to Redis or Kafka for near‑real‑time streaming. See the Grafana documentation for instructions on configuring those plugins.

Querying via the LLM‑based Flowcept Agent
-----------------------------------------

Flowcept’s agentic querying (powered by language models) is under active development. The agent will allow natural‑language queries over provenance data, with interactive guidance and summarisation. Documentation will be released in a future version. In the meantime, use the CLI or Python API for querying tasks and workflows.

Conclusion
----------

Flowcept offers several ways to query provenance data depending on your environment and requirements. For quick inspection, use the in‑memory buffer or offline message files. For interactive scripts or notebooks, `Flowcept.db` provides a high‑level API to MongoDB or LMDB. For more sophisticated queries, connect directly to MongoDB using the CLI or standard MongoDB tools. Grafana integration lets you build dashboards on live data. As Flowcept evolves, additional capabilities—such as LLM‑based query agents—will expand the ways you can explore your provenance.
