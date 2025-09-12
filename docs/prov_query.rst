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

Accessing the In‑Memory Buffer
------------------------------

During runtime Flowcept stores captured messages in an in‑memory buffer (`Flowcept.buffer`). This buffer is useful for debugging or lightweight scripts because it provides immediate access to the latest tasks and workflows without any additional services. However, if running online, be aware that this buffer is flushed (i.e., emptied) from times to times to the MQ.

In the example below we create two tasks that attach binary data and then inspect the buffer:

.. code-block:: python

    from pathlib import Path
    from flowcept import Flowcept
    from flowcept.instrumentation.task import FlowceptTask

    with Flowcept() as f:
        used_args = {"a": 1}
        # first task – attach a PDF
        with FlowceptTask(used=used_args) as t:
            img_path = Path("docs/img/architecture.pdf")
            with open(img_path, "rb") as fp:
                img_data = fp.read()
            t.end(generated={"b": 2},
                  data=img_data,
                  custom_metadata={
                      "mime_type": "application/pdf",
                      "file_name": "architecture.pdf",
                      "file_extension": "pdf"})
            t.send()
        # second task – attach a PNG
        with FlowceptTask(used=used_args) as t:
            img_path = Path("docs/img/flowcept-logo.png")
            with open(img_path, "rb") as fp:
                img_data = fp.read()
            t.end(generated={"c": 2},
                  data=img_data,
                  custom_metadata={
                      "mime_type": "image/png",
                      "file_name": "flowcept-logo.png",
                      "file_extension": "png"})
            t.send()

        # inspect the buffer
        assert len(Flowcept.buffer) == 3  # includes the workflow message
        assert Flowcept.buffer[1]["data"]  # binary data is captured as bytes

At any point inside the running workflow you can access `Flowcept.buffer` to retrieve a list of dictionaries representing messages. Each element contains the original JSON payload plus any binary `data` field. Because the buffer lives in memory, it reflects the most recent state of the workflow and is cleared when the process ends.

Working Offline: Reading a Messages File
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When persistence is enabled in offline mode, Flowcept dumps the buffer to a JSONL file. Use :func:`Flowcept.read_messages_file` to load these messages later. If you pass `return_df=True` Flowcept will normalise nested fields into dot‑separated columns and return a pandas DataFrame. This is handy for ad‑hoc analysis with pandas.

.. code-block:: python

    from flowcept import Flowcept

    # read JSON into a list of dicts
    msgs = Flowcept.read_messages_file("offline_buffer.jsonl")
    print(f"{len(msgs)} messages")

    # read JSON into a pandas DataFrame
    df = Flowcept.read_messages_file("offline_buffer.jsonl", return_df=True)
    # dot‑notation columns allow easy selection; e.g., outputs of attention layers
    print("generated.attention" in df.columns)

Keep in mind that the JSONL file is only created when using fully offline mode. The path is configured in the settings file under ``DUMP_BUFFER_PATH``. If the file doesn’t exist, `read_messages_file` will raise an error.


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
