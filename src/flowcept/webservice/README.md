# Flowcept Webservice

This package contains the new read-only REST API layer for Flowcept.

## Scope

- Read-only endpoints for `workflows`, `tasks`, and `objects`
- Query endpoints for advanced filtering/projection/sort/aggregation
- OpenAPI-first delivery through FastAPI (`/openapi.json`, `/docs`, `/redoc`)
- No ingestion/write endpoints in v1

## Package Structure

- `main.py`: FastAPI app factory and router registration
- `deps.py`: dependency injection helpers (currently `DBAPI`)
- `routers/`: endpoint modules by resource
  - `health.py`
  - `workflows.py`
  - `tasks.py`
  - `objects.py`
- `schemas/`: request/response payload models
  - `common.py`
- `services/`: reusable service utilities
  - `serializers.py`
- `docs/`: implementation and API contract docs for maintainers

## Runtime behavior

The webservice delegates all database reads to `flowcept.flowcept_api.db_api.DBAPI`.

- Connection/backend selection stays centralized in existing Flowcept config (`flowcept.configs`)
- This package does not define a separate config system
- Host/port exposed in root response come from `WEBSERVER_HOST` and `WEBSERVER_PORT`

## Base path

All API routes are mounted under:

- `/api/v1`

## API summary

### Health

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`

### Workflows

- `GET /api/v1/workflows`
- `GET /api/v1/workflows/{workflow_id}`
- `POST /api/v1/workflows/query`
- `POST /api/v1/workflows/{workflow_id}/reports/provenance-card/download`

### Tasks

- `GET /api/v1/tasks`
- `GET /api/v1/tasks/{task_id}`
- `GET /api/v1/tasks/by_workflow/{workflow_id}`
- `POST /api/v1/tasks/query`

### Objects

- `GET /api/v1/objects`
- `GET /api/v1/objects/{object_id}`
- `GET /api/v1/objects/{object_id}/versions/{version}`
- `GET /api/v1/objects/{object_id}/download`
- `GET /api/v1/objects/{object_id}/versions/{version}/download`
- `GET /api/v1/objects/{object_id}/history`
- `POST /api/v1/objects/query`

### Datasets

- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{object_id}`
- `GET /api/v1/datasets/{object_id}/versions/{version}`
- `GET /api/v1/datasets/{object_id}/download`
- `POST /api/v1/datasets/query`

### Models

- `GET /api/v1/models`
- `GET /api/v1/models/{object_id}`
- `GET /api/v1/models/{object_id}/versions/{version}`
- `GET /api/v1/models/{object_id}/download`
- `POST /api/v1/models/query`

### Unified scoped query

- `POST /api/v1/query/{scope}`
- Supported `scope`: `workflows | tasks | objects | models | datasets`
- `models` and `datasets` enforce fixed base filters (`object_type=ml_model` and `object_type=dataset`)

## Query model

Advanced `POST /query` endpoints share a common request model:

```json
{
  "filter": {"workflow_id": "wf_123"},
  "projection": ["task_id", "started_at"],
  "limit": 100,
  "sort": [{"field": "started_at", "order": -1}],
  "aggregation": [{"operator": "max", "field": "ended_at"}],
  "remove_json_unserializables": true
}
```

### Semantics

- `filter`: backend query filter document
- `projection`: list of field names to include
- `limit`: max number of docs returned (bounded in schema)
- `sort`: ordered field directions (`1` ascending, `-1` descending)
- `aggregation`: optional aggregate operations (`avg`, `sum`, `min`, `max`)
- `remove_json_unserializables`: pass-through behavior for DAO task/workflow queries

`objects/query` also supports:

- `include_data` (default `false`): include binary payload if available (base64 encoded)

## Response shape

List endpoints return:

```json
{
  "items": [],
  "count": 0,
  "limit": 100
}
```

Single-resource endpoints return one normalized document object.

## Serialization rules

`services/serializers.py` normalizes non-JSON-native values recursively:

- `datetime` -> ISO8601 string
- `ObjectId` -> string
- `bytes` -> base64 string (only when payload inclusion is enabled)
- unknown objects -> string fallback

For object metadata endpoints, `data` is excluded by default.

## Error handling

- Invalid JSON in `filter_json` -> `400`
- Missing resource -> `404`
- DAO validation/value errors -> `400` (or `404` where endpoint maps not-found)

## Running locally

```bash
uvicorn flowcept.webservice.main:app --host 0.0.0.0 --port 5000
```

Swagger and OpenAPI are then available at:

- `/docs`
- `/redoc`
- `/openapi.json`

## OpenAPI artifact generation

Generate static OpenAPI files for docs publishing:

```bash
python docs/openapi/scripts/generate_openapi.py
```

Outputs:

- `docs/openapi/flowcept-openapi.json`
- `docs/openapi/flowcept-openapi.yaml`

## Extension roadmap

When you add write endpoints later:

1. Keep read/write routers split (`routers/read_*`, `routers/write_*`) or by resource with clear tags.
2. Introduce authN/authZ middleware before enabling writes.
3. Add explicit optimistic concurrency/version checks for object updates.
4. Add audit logging for mutating operations.
5. Add contract tests using FastAPI `TestClient`.
