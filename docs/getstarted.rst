Getting Started
===============

Quick Install
----------------------------------------------------------------------------------------------

To install Flowcept with its default dependencies, simply run:

.. code-block:: bash

   pip install flowcept

On your Python environment.
This will install the core Flowcept package. For additional adapters or features (e.g., MongoDB, Kafka, MLFlow, Dask), see the `README.md <https://github.com/ORNL/flowcept#installation>`_ for instructions on installing extra dependencies.


Start Up Services
----------------------------------------------------------------------------------------------

To start required services like the default Redis MQ system, use the provided Makefile target:

.. code-block:: bash

   make services

This will launch the necessary message queue services for running Flowcept.

If you need MongoDB, you'll run:

.. code-block:: bash

   make services-mongo


For more options, see the `deployment directory <https://github.com/ORNL/flowcept/tree/main/deployment>`_.

Customizing Settings
----------------------------------------------------------------------------------------------

Flowcept allows extensive configuration via a YAML file. To use a custom configuration, set the environment variable
``FLOWCEPT_SETTINGS_PATH`` to point to the absolute path of your settings file. A sample file is provided at For more options, see the `sample_settings.yaml <https://github.com/ORNL/flowcept/blob/main/resources/sample_settings.yaml>`_.

Key Settings to Adjust
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


- **Service Connections:** Set host, port, and credentials for MQ (`mq:`), key-value DB (`kv_db:`), and optionally MongoDB (`mongodb:`).
- **Telemetry:** Toggle `cpu`, `mem`, `gpu`, `disk`, `network`, and `process_info` under `telemetry_capture:`.
- **Instrumentation:** Enable and control ML model tracing under `instrumentation:` (especially `torch:` for PyTorch).
- **Debug & Logging:** Use `project.debug`, `log.log_file_level`, and `log.log_stream_level` to control output and verbosity.

Note that if using Redis, MQ and KV_DB are have same host. Refer to the sample settings file for full options and examples.



Usage Example with Instrumentation
----------------------------------------------------------------------------------------------

Flowcept supports decorator-based instrumentation for capturing workflow execution data. Here's a simple example:

.. code-block:: python

   from flowcept import Flowcept, flowcept_task

   @flowcept_task
   def sum_one(n):
       return n + 1

   @flowcept_task
   def mult_two(n):
       return n * 2

   with Flowcept(workflow_name='test_workflow'):
       n = 3
       o1 = sum_one(n)
       o2 = mult_two(o1)
       print(o2)

   print(Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id}))


Usage with Data Observability Adapters
----------------------------------------------------------------------------------------------

Flowcept includes adapters for MLFlow, Dask, and TensorBoard that can automatically capture provenance data.

For detailed usage and example configurations, refer to the `examples directory <https://github.com/ORNL/flowcept/tree/main/examples>`_.


Querying
----------------------------------------------------------------------------------------------

Once data is captured and persisted (e.g., to MongoDB), you can use Flowcept’s query interface:

.. code-block:: python

   from flowcept import Flowcept

   results = Flowcept.db.query({"workflow_id": "<some_workflow_id>"})
   print(results)

The query API enables flexible inspection of captured data. Note: MongoDB must be enabled for this feature.


Installation and usage instructions are detailed in the following sections.
