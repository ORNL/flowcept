API Reference
=============

.. autosummary::
   :toctree: generated/
   :recursive:

   flowcept.Flowcept
   flowcept.flowcept_api.db_api.DBAPI
   flowcept.TaskObject
   flowcept.WorkflowObject
   flowcept.FlowceptTask
   flowcept.FlowceptLoop
   flowcept.FlowceptLightweightLoop

Main Flowcept Object
--------------------

.. autoclass:: flowcept.Flowcept
   :members:
   :special-members: __init__
   :exclude-members: __weakref__, __dict__, __module__



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


Main Message Objects
---------------------

.. autoclass:: flowcept.TaskObject
   :members:

.. autoclass:: flowcept.WorkflowObject
   :members:

FlowceptTask object
-------------------

.. autoclass:: flowcept.FlowceptTask
   :members:
   :special-members: __init__
   :undoc-members:
   :show-inheritance:

FlowceptLoop object
-------------------

.. autoclass:: flowcept.FlowceptLoop
   :members:
   :special-members: __init__
   :undoc-members:
   :show-inheritance:


FlowceptLightweightLoop object
------------------------------

.. autoclass:: flowcept.FlowceptLightweightLoop
   :members:
   :special-members: __init__
   :undoc-members:
   :show-inheritance: