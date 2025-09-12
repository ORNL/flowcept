API Reference
=============


Main Flowcept Object
--------------------

See also: `Flowcept object <https://flowcept.readthedocs.io/en/latest/prov_capture.html>`_ in provenance capture methods.

.. autoclass:: flowcept.Flowcept
   :members:
   :special-members: __init__
   :exclude-members: __weakref__, __dict__, __module__
   :noindex:

Flowcept.db: Querying the Database
----------------------------------

The ``Flowcept.db`` property exposes an instance of :class:`flowcept.flowcept_api.db_api.DBAPI`,
providing high-level methods to query, insert, and update provenance data in the configured database.

Typical usage:

.. code-block:: python

   from flowcept import Flowcept

   # Query tasks from the current workflow
   tasks = Flowcept.db.get_tasks_from_current_workflow()

   # Query workflows
   workflows = Flowcept.db.workflow_query({"name": "my_workflow"})

   # Insert or update a task/workflow
   Flowcept.db.insert_or_update_task(my_task_obj)
   Flowcept.db.insert_or_update_workflow(my_wf_obj)

.. autoclass:: flowcept.flowcept_api.db_api.DBAPI
   :members:
   :undoc-members:
   :show-inheritance:
   :noindex:

Main Message Objects
---------------------

.. autoclass:: flowcept.TaskObject
   :members:
   :noindex:

.. autoclass:: flowcept.WorkflowObject
   :members:
   :noindex:

FlowceptTask
-------------------

.. autoclass:: flowcept.FlowceptTask
   :members:
   :special-members: __init__
   :undoc-members:
   :show-inheritance:
   :noindex:

FlowceptLoop
-------------------

.. autoclass:: flowcept.FlowceptLoop
   :members:
   :special-members: __init__
   :undoc-members:
   :show-inheritance:
   :noindex:

FlowceptLightweightLoop
------------------------------

.. autoclass:: flowcept.FlowceptLightweightLoop
   :members:
   :special-members: __init__
   :undoc-members:
   :show-inheritance:
   :noindex:
