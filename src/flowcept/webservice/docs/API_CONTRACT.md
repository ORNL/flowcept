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

### POST /api/v1/workflows/{workflow_id}/reports/workflow-card/download

Generates a workflow card markdown report for the workflow and downloads it as an attachment.

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

### Datasets (`type=dataset`)

- `GET /api/v1/datasets`
- `GET /api/v1/datasets/{object_id}`
- `GET /api/v1/datasets/{object_id}/versions/{version}`
- `GET /api/v1/datasets/{object_id}/download`
- `POST /api/v1/datasets/query`

### Models (`type=ml_model`)

- `GET /api/v1/models`
- `GET /api/v1/models/{object_id}`
- `GET /api/v1/models/{object_id}/versions/{version}`
- `GET /api/v1/models/{object_id}/download`
- `POST /api/v1/models/query`

### POST /api/v1/query/{scope}

Unified scoped read-only query endpoint.

- `scope`: `workflows | tasks | objects | models | datasets`
- Uses the same query body model as other `/query` routes.
- `models` and `datasets` scopes enforce fixed type filters.
- Rejects unsupported filter operators.

### Campaigns (derived; no campaigns collection)

- `GET /api/v1/campaigns` — grouped from workflows/tasks by `campaign_id`
- `GET /api/v1/campaigns/{campaign_id}` — `{campaign, workflows, task_summary}`; 404 when nothing matches
- `GET /api/v1/campaigns/{campaign_id}/workflow_card?format=json|markdown`

### Agents (derived from task `agent_id`/`source_agent_id`)

- `GET /api/v1/agents`
- `GET /api/v1/agents/{agent_id}` — `{agent, task_summary}`
- `GET /api/v1/agents/{agent_id}/tasks`

### Stats

- `GET /api/v1/stats/tasks/summary` — `{count, status_counts, activity_stats, time_range}`
- `POST /api/v1/stats/timeseries` — body `{filter, fields: [dot-paths], x, limit}` → `{rows, count}`
- `POST /api/v1/stats/card_data` — body `{data: CardData, context}` → `{rows, count}`;
  `CardData` is the declarative dashboard binding (`source, filter, group_by, metrics | x/y, sort, limit`)

### Dashboards

- `GET /api/v1/dashboards`, `POST /api/v1/dashboards` (201; server assigns `dashboard_id`)
- `GET|PUT|DELETE /api/v1/dashboards/{dashboard_id}`
- Specs validated against `schemas/dashboards.py::DashboardSpec`; card/context filters use the
  same operator allowlist as `/query`

### Provenance cards

- `GET /api/v1/workflows/{workflow_id}/workflow_card?format=json|markdown`
- `format=json` returns `{dataset, transformations, object_summary, input_mode}`

### Live streams (SSE)

- `GET /api/v1/stream/tasks?workflow_id=&campaign_id=&agent_id=&since=&poll_interval=`
- `GET /api/v1/stream/workflows?campaign_id=&since=&poll_interval=`
- `text/event-stream`; events named `tasks`/`workflows` with data
  `{tasks|workflows: [...], cursor: float, truncated: bool}`; pass `cursor` back as `since` to resume.
  Backed by incremental DB polling (`web_server.sse_*` settings); no MQ coupling.

### POST /api/v1/chat

- Body: `{messages: [{role, content}], context, stream, allow_dashboard_edit}` (stateless;
  client passes history)
- `stream=true`: SSE events `tool_call`, `tool_result`, `card`, `token`, `done`, `error`
- `stream=false`: one JSON `{message, tool_trace, cards}`
- LLM built from the `agent` settings section; `503` when not configured
- Tools are the shared provenance core (`flowcept.agents.tools.prov_tools`), also exposed via the
  MCP agent as `query_provenance_tasks`, `list_provenance_campaigns`, etc.

## Status codes

- `200`: success
- `201`: dashboard created
- `400`: malformed input or unsupported query shape
- `404`: resource does not exist
- `422`: request schema validation error (FastAPI/Pydantic)
- `500`: unexpected internal error
- `503`: chat requested but no LLM configured/available
