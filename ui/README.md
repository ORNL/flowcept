# Flowcept Web UI

React single-page application for browsing and analyzing Flowcept provenance data:
campaigns, workflows, tasks, artifacts (datasets/ML models), and agents — with live (SSE)
updates, per-workflow/campaign dashboards, and an embedded LLM chat that queries the
provenance database and renders charts.

The UI is served by the Flowcept webservice (FastAPI, `src/flowcept/webservice/`). Built
assets are emitted into the Python package (`src/flowcept/webservice/ui_build/`) so released
wheels ship the UI; end users need no Node toolchain.

**Quick start:**
```bash
make ui-install && make ui-build
flowcept --start-ui        # webservice + Vite dev server; open http://localhost:8008
```

---

## Dashboard data model

Chart configurations are stored server-side in the MongoDB `dashboards` collection (or as
JSON files when Mongo is unavailable). They are managed via `GET/POST/PUT/DELETE /api/v1/dashboards`.

There are four schema types:

| Type | Applies to | Matched by |
|---|---|---|
| `common_workflow` | every workflow's Dashboard tab | — |
| `common_campaign` | every campaign's Dashboard tab | — |
| `custom_workflow` | a specific workflow (by name) | `target == workflow.name` |
| `custom_campaign` | a specific campaign | `target == campaign_id` |

Default schemas are seeded from `src/flowcept/webservice/ui_build/default_dashboard_configs.json`
on first run. **When you edit `ui/public/default_dashboard_configs.json` you must also copy it
to `src/flowcept/webservice/ui_build/` and push the update to MongoDB:**
```bash
cp ui/public/default_dashboard_configs.json src/flowcept/webservice/ui_build/default_dashboard_configs.json
python -c "
import json
from flowcept.webservice.services.dashboard_store import get_dashboard_store
store = get_dashboard_store()
for doc in json.load(open('src/flowcept/webservice/ui_build/default_dashboard_configs.json')):
    store.save(doc)
"
```

### Schema types

```
DashboardConfig
  dashboard_id   : string (uuid, server-assigned)
  dashboard_type : "common_workflow" | "common_campaign" | "custom_workflow" | "custom_campaign"
  target         : string | null   # workflow name or campaign_id for custom types
  name           : string
  charts         : Chart[]

Chart
  chart_id  : string
  type      : "chart" | "metric" | "table" | "markdown"
  title     : string
  live      : bool           # auto-refresh
  data      : ChartData      # not used for markdown
  viz       : { kind: "bar" | "line" | "pie" | "scatter" | "area", stacked?: bool }
  content   : string         # markdown body (markdown type only)

ChartData
  source    : "tasks" | "workflows" | "objects" | "collection_sizes"
  filter    : {}             # Mongo-style filter; ANDed with the dashboard context
  group_by  : string         # dot-path field (e.g. "activity_id")
  metrics   : [{ field: string, agg: "count"|"avg"|"sum"|"min"|"max" }]
  x / y     : string / string[]   # for scatter/line charts
  limit     : 1–5000
```

**Context:** each chart's filter is automatically scoped to the current workflow or campaign
via `context.workflow_id` / `context.campaign_id`.

**`collection_sizes` source:** a virtual source that returns BSON byte totals across the
`tasks`, `objects`, and `workflows` collections for the given context — used for the
"Data per collection" chart.

**Auto-hide:** charts that return zero rows are hidden by default. Toggle pills above the
grid let users show/hide any chart.

**Inspector:** clicking a chart pushes its raw data rows to the right-panel Inspector as a
formatted table.

---

## Stack

| Concern | Library |
|---|---|
| Build / dev server | Vite + TypeScript strict |
| UI framework | React 18 |
| Styling | Tailwind CSS 4 (dark theme via CSS variables in `src/index.css`) |
| Routing | TanStack Router (file-based, typed search params — all view state in the URL) |
| Server state | TanStack Query v5 |
| Tables | TanStack Table + Virtual (virtualized task tables) |
| Charts | Apache ECharts (`echarts/core`, tree-shaken; `components/charts/EChart.tsx` wrapper) |
| Dashboards grid | react-grid-layout v2 (drag/resize) |
| Markdown | react-markdown + remark-gfm + rehype-raw (provenance cards, chat) |
| SSE | @microsoft/fetch-event-source (supports POST for chat streaming) |
| Validation | zod (dashboard specs, route search params) |
| Ephemeral state | zustand (chat panel, inspector panel) |

---

## Code layout

```
ui/
  vite.config.ts          # dev proxy (/api → :8008), build.outDir → ../src/flowcept/webservice/ui_build
  public/
    default_dashboard_configs.json   # source of truth for default chart schemas
    flowcept-logo.png
  src/
    main.tsx              # router + query client setup
    index.css             # Tailwind theme tokens (colors, card/prose utility classes)
    api/
      client.ts           # fetch wrapper for /api/v1 (apiGet/apiPost/apiPut/apiDelete)
      types.ts            # hand-maintained API types
      queries.ts          # TanStack Query hooks (useCampaigns, useWorkflow, useTasksQuery, ...)
      sse.ts              # useEventStream: cursor resume, backoff, tab-pause
    lib/
      format.ts           # toEpochSec / fmtTs / fmtDuration / fmtBytes / statusColor
    stores/
      inspectorStore.ts   # right-panel inspector state (task / artifact / chart data)
      chatStore.ts        # chat transcript + panel visibility
    components/
      charts/             # EChart wrapper, GanttChart, DagView, DataflowView, StatusStrip, TelemetryChart
      tables/DataTable.tsx# virtualized generic table (TanStack Table + Virtual)
      markdown/           # Markdown renderer (rehype-raw for HTML in prov cards)
      JsonTree.tsx        # collapsible JSON tree
      DeleteConfirmModal.tsx
      dashboard/
        spec.ts           # zod mirror of webservice schemas/dashboards.py
        specToOption.ts   # ChartData + rows → ECharts option
        ChartRenderer.tsx # per-type chart rendering; data via POST /api/v1/stats/chart_data
    routes/
      __root.tsx          # app shell: sidebar + resizable panels + inspector + chat slot
      index.tsx           # overview page
      campaigns.index.tsx / campaigns.$campaignId.tsx
      workflows.index.tsx / workflows.$workflowId.tsx
      tasks.$taskId.tsx
      objects.index.tsx / objects.$objectId.tsx
      agents.index.tsx
      dashboards.index.tsx / dashboards.$dashboardId.tsx
```

---

## Running

### Prerequisites

- Flowcept installed with `[webservice]` extra.
- Redis + MongoDB running (`make services-mongo`).
- Node 22+ and npm for development/build only.

### Production-style (bundled)

```bash
make ui-install   # once: npm ci --prefix ui
make ui-build     # emits assets into src/flowcept/webservice/ui_build/
flowcept --start-webservice   # serves UI + API on :8008
# open http://localhost:8008
```

### Development (hot reload)

```bash
make ui    # kills old processes, starts webservice in background + Vite dev server in foreground
           # UI:  http://localhost:5173  (proxies /api → :8008)
           # API: http://localhost:8008
```

Or manually:
```bash
# terminal 1 — API:
PYTHONPATH=src python -m flowcept.cli --start-webservice

# terminal 2 — UI dev server:
npm run dev --prefix ui
```

### Configurable ports

| Environment variable | Default | Purpose |
|---|---|---|
| `WEBSERVER_HOST` | `0.0.0.0` | FastAPI bind host |
| `WEBSERVER_PORT` | `8008` | FastAPI bind port |
| `VITE_API_HOST` | `localhost` | API host the Vite proxy forwards to |
| `VITE_API_PORT` | `8008` | API port the Vite proxy forwards to |
| `VITE_DEV_PORT` | `5173` | Vite dev server listen port |

### Enabling the chat (LLM)

```yaml
# ~/.flowcept/settings.yaml
agent:
  enabled: true
  service_provider: openai   # sambanova | azure | openai | google
  llm_server_url: <endpoint>
  api_key: <key>
  model: <model name>
web_server:
  chat:
    enabled: true
    max_tool_iterations: 5
    max_query_limit: 1000
```

Without this, `POST /api/v1/chat` returns 503 and the rest of the UI works normally.

---

## Tests

Integration tests (real services, no mocks) are in
`tests/webservice/test_webservice_integration.py`.

Run with live services:
```bash
PYTHONPATH=src conda run -n flowcept python -m pytest tests/webservice/
```
