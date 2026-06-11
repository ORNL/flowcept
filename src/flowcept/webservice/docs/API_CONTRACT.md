# API Contract (v1)

## Versioning

- URL versioning: `/api/v1`
- Backward-incompatible changes require `/api/v2`

## Resource model

- `workflows`: workflow-level provenance records
- `tasks`: task-level provenance records
- `objects`: blob metadata and versioned object records

## Default ordering

List endpoints for workflows, tasks, and objects are ordered ascending by the first available date/timestamp field.

## Endpoint details

### GET /api/v1/workflows

Query params:

- `limit` (1..1000)
- `user`
- `campaign_id`
- `parent_workflow_id`
- `name`
- `filter_json` (JSON object encoded as string)

### GET /api/v1/workflows/{workflow_id}

Returns one workflow or `404`.

### POST /api/v1/workflows/query

Request body: shared query model.

### POST /api/v1/workflows/{workflow_id}/reports/provenance-card/download

Generates a provenance card markdown report for the workflow and downloads it as an attachment.

### GET /api/v1/tasks

Query params:

- `limit` (1..1000)
- `workflow_id`
- `parent_task_id`
- `campaign_id`
- `task_id`
- `status`
- `filter_json`

### GET /api/v1/tasks/{task_id}

Returns one task or `404`.

### GET /api/v1/tasks/by_workflow/{workflow_id}

Returns tasks for a workflow.

### POST /api/v1/tasks/query

Supports `filter`, `projection`, `sort`, `limit`, `aggregation`.

Validation rule:

- if `aggregation` is provided, `projection` may include at most one field

### GET /api/v1/objects

Query params:

- `limit` (1..1000)
- `object_id`
- `workflow_id`
- `task_id`
- `type`
- `filter_json`
- `include_data` (`false` by default)

### GET /api/v1/objects/{object_id}

Returns latest object metadata (plus data only when `include_data=true`).

### GET /api/v1/objects/{object_id}/versions/{version}

Returns specific object version or `404`.

### GET /api/v1/objects/{object_id}/download

Downloads latest object payload bytes as `application/octet-stream`.

### GET /api/v1/objects/{object_id}/versions/{version}/download

Downloads specific object version payload bytes as `application/octet-stream`.

### GET /api/v1/objects/{object_id}/history

Returns version history metadata sorted latest-first.

### POST /api/v1/objects/query

Same query model as above, plus `include_data`.

### Datasets (`object_type=dataset`)

- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{object_id}`
- `GET /api/v1/datasets/{object_id}/versions/{version}`
- `GET /api/v1/datasets/{object_id}/download`
- `POST /api/v1/datasets/query`

### Models (`object_type=ml_model`)

- `GET /api/v1/models`
- `GET /api/v1/models/{object_id}`
- `GET /api/v1/models/{object_id}/versions/{version}`
- `GET /api/v1/models/{object_id}/download`
- `POST /api/v1/models/query`

### POST /api/v1/query/{scope}

Unified scoped read-only query endpoint.

- `scope`: `workflows | tasks | objects | models | datasets`
- Uses the same query body model as other `/query` routes.
- `models` and `datasets` scopes enforce fixed `object_type` filters.
- Rejects unsupported filter operators.

## Status codes

- `200`: success
- `400`: malformed input or unsupported query shape
- `404`: resource does not exist
- `422`: request schema validation error (FastAPI/Pydantic)
- `500`: unexpected internal error
