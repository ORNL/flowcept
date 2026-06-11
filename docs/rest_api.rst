REST API
========

Flowcept provides a read-only REST API for querying provenance data from MongoDB.

Default list ordering
---------------------

List endpoints for workflows, tasks, and objects return results sorted ascending by the first available date/timestamp field.

Base URL
--------

- ``/api/v1``

Interactive API docs
--------------------

- Swagger UI: ``/docs``
- ReDoc: ``/redoc``
- OpenAPI JSON: ``/openapi.json``

Run locally
-----------

.. code-block:: bash

   uvicorn flowcept.webservice.main:app --host 0.0.0.0 --port 5000

Endpoints
---------

- Health
  - ``GET /api/v1/health/live``
  - ``GET /api/v1/health/ready``
- Workflows
  - ``GET /api/v1/workflows``
  - ``GET /api/v1/workflows/{workflow_id}``
  - ``POST /api/v1/workflows/query``
  - ``POST /api/v1/workflows/{workflow_id}/reports/provenance-card/download``
- Tasks
  - ``GET /api/v1/tasks``
  - ``GET /api/v1/tasks/{task_id}``
  - ``GET /api/v1/tasks/by_workflow/{workflow_id}``
  - ``POST /api/v1/tasks/query``
- Objects
  - ``GET /api/v1/objects``
  - ``GET /api/v1/objects/{object_id}``
  - ``GET /api/v1/objects/{object_id}/versions/{version}``
  - ``GET /api/v1/objects/{object_id}/download``
  - ``GET /api/v1/objects/{object_id}/versions/{version}/download``
  - ``GET /api/v1/objects/{object_id}/history``
  - ``POST /api/v1/objects/query``
- Datasets
  - ``GET /api/v1/datasets``
  - ``GET /api/v1/datasets/{object_id}``
  - ``GET /api/v1/datasets/{object_id}/versions/{version}``
  - ``GET /api/v1/datasets/{object_id}/download``
  - ``POST /api/v1/datasets/query``
- Models
  - ``GET /api/v1/models``
  - ``GET /api/v1/models/{object_id}``
  - ``GET /api/v1/models/{object_id}/versions/{version}``
  - ``GET /api/v1/models/{object_id}/download``
  - ``POST /api/v1/models/query``

Query endpoint body
-------------------

.. code-block:: json

   {
     "filter": {"workflow_id": "wf_123"},
     "projection": ["task_id", "started_at", "ended_at"],
     "sort": [{"field": "started_at", "order": -1}],
     "limit": 100,
     "aggregation": null
   }

OpenAPI artifact
----------------

Generate static OpenAPI files:

.. code-block:: bash

   python docs/openapi/scripts/generate_openapi.py

Files generated:

- ``docs/openapi/flowcept-openapi.json``
- ``docs/openapi/flowcept-openapi.yaml``

ReadTheDocs OpenAPI downloads
-----------------------------

Because ``docs/conf.py`` includes ``html_extra_path = [\"openapi\"]``, the files are published at the documentation
root on ReadTheDocs and can be downloaded from:

- ``https://flowcept.readthedocs.io/en/latest/flowcept-openapi.yaml``
- ``https://flowcept.readthedocs.io/en/latest/flowcept-openapi.json``
