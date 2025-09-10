Quick Start
===========

.. toctree::
   :maxdepth: 2
   :caption: Contents:


The easiest way to capture provenance from plain Python functions—no external services required.

Install and Initialize
----------------------

First, install Flowcept and initialize a settings file:

.. code-block:: bash

   # Make sure you activate your Python environment (conda, venv, etc.)
   pip install flowcept
   flowcept --init-settings

This creates a minimal settings file at ``~/.flowcept/settings.yaml``.

Run a Minimal Example
---------------------

Save the following script as ``quickstart.py`` and run ``python quickstart.py``:

.. code-block:: python

   """
   Minimal example of Flowcept's instrumentation using decorators.
   No DB, broker, or external service required.
   """
   import json

   from flowcept import Flowcept, flowcept_task
   from flowcept.instrumentation.flowcept_decorator import flowcept


   @flowcept_task(output_names="o1")
   def sum_one(i1):
       return i1 + 1


   @flowcept_task(output_names="o2")
   def mult_two(o1):
       return o1 * 2


   @flowcept
   def main():
       n = 3
       o1 = sum_one(n)
       o2 = mult_two(o1)
       print("Final output", o2)


   if __name__ == "__main__":
       main()

       prov_messages = Flowcept.read_messages_file()
       assert len(prov_messages) == 2
       print(json.dumps(prov_messages, indent=2))

Inspecting the Output
---------------------

Flowcept writes provenance messages to ``flowcept_messages.jsonl``.  
You should see two messages, each describing one executed task:

.. code-block:: json

   [
     {
       "activity_id": "sum_one",
       "workflow_id": "fe546706-ef46-4482-8f70-3af664a7131b",
       "campaign_id": "76088532-3bef-4343-831e-d8a5d9156174",
       "used": {"i1": 3},
       "generated": {"o1": 4},
       "status": "FINISHED",
       "type": "task"
     },
     {
       "activity_id": "mult_two",
       "workflow_id": "fe546706-ef46-4482-8f70-3af664a7131b",
       "campaign_id": "76088532-3bef-4343-831e-d8a5d9156174",
       "used": {"o1": 4},
       "generated": {"o2": 8},
       "status": "FINISHED",
       "type": "task"
     }
   ]

Next Steps
----------

For advanced usage, including:

- Online querying with databases (MongoDB, LMDB)
- MCP agents and Grafana dashboards
- Telemetry capture
- Adapters (MLflow, Dask, TensorBoard)
- PyTorch instrumentation
- HPC optimization or federated runs

see:

- `Jupyter Notebooks <https://github.com/ORNL/flowcept/tree/main/notebooks>`_
- `Examples directory <https://github.com/ORNL/flowcept/tree/main/examples>`_
- `Complete documentation <https://flowcept.readthedocs.io/>`_
