# Flowcept Web UI

React single-page app for browsing and analyzing Flowcept provenance data: campaigns,
workflows, tasks, artifacts (datasets/ML models), and agents — with live (SSE) updates,
user-defined dashboards, and an embedded LLM chat that queries the provenance database
and renders charts.

The UI is served by the Flowcept webservice (FastAPI, `src/flowcept/webservice/`). The built
assets are emitted into the Python package (`src/flowcept/webservice/ui_build/`) so released
wheels ship the UI; end users need no Node toolchain.

## Stack

| Concern | Library |
|---|---|
| Build/dev server | Vite + TypeScript (strict) |
| UI framework | React 18 |
| Styling | Tailwind CSS 4 (dark theme via CSS variables in `src/index.css`) |
| Routing | TanStack Router (file-based routes, typed search params — all view state is in the URL) |
| Server state | TanStack Query |
| Tables | TanStack Table + Virtual (virtualized task tables) |
| Charts | Apache ECharts (`echarts/core`, tree-shaken; thin wrapper in `components/charts/EChart.tsx`) |
| Dashboards grid | react-grid-layout v2 (drag/resize) |
| Markdown | react-markdown + remark-gfm (provenance cards, chat) |
| SSE | @microsoft/fetch-event-source (supports POST bodies for chat) |
| Validation | zod (dashboard specs, search params) |
| Ephemeral state | zustand (chat panel) |

## Code layout

```
ui/
  vite.config.ts          # dev proxy (/api → :5000), build.outDir → ../src/flowcept/webservice/ui_build
  src/
    main.tsx              # router + query client setup
    index.css             # Tailwind theme tokens (colors, card/prose utility classes)
    api/
      client.ts           # fetch wrapper for /api/v1 (apiGet/apiPost/apiPut/apiDelete)
      types.ts            # hand-maintained API types (regenerate: npm run gen-api-types)
      queries.ts          # TanStack Query hooks (useCampaigns, useWorkflow, useTasksQuery, ...)
      sse.ts              # useEventStream: SSE hook w/ cursor resume, backoff, tab-pause
    lib/format.ts         # toEpochSec/fmtTs/fmtDuration/statusColor (handles float AND ISO times)
    stores/chatStore.ts   # chat transcript + panel state
    components/
      charts/             # EChart wrapper, GanttChart (custom series), StatusStrip, TelemetryChart
      tables/DataTable.tsx# virtualized generic table
      markdown/, JsonTree.tsx, tasks/TaskDrawer.tsx
      dashboard/
        spec.ts           # zod mirror of webservice schemas/dashboards.py (DashboardSpec/Card/CardData)
        specToOption.ts   # declarative card spec + rows → ECharts option
        CardRenderer.tsx  # per-type card rendering; data via POST /api/v1/stats/card_data
      chat/ChatPanel.tsx  # streams POST /api/v1/chat SSE events into rich message parts
    routes/               # file-based pages: __root (shell+sidebar+chat), index (overview),
                          # campaigns, workflows.$workflowId (tasks/timeline/telemetry/card/raw tabs),
                          # tasks.$taskId, objects, agents, dashboards.$dashboardId (grid editor)
```

Data-flow summary:

- Pages call REST endpoints under `/api/v1` (see `src/flowcept/webservice/docs/API_CONTRACT.md`).
- Live mode (the `LIVE` toggle on a workflow page, or `live: true` dashboard cards) uses
  `GET /api/v1/stream/tasks` — SSE backed by incremental DB polling; the `cursor` in each event
  resumes the stream after reconnects.
- Dashboards are JSON specs stored server-side (`/api/v1/dashboards`); each card declares a
  data binding (`CardData`) resolved by `POST /api/v1/stats/card_data` and mapped to ECharts.
- Chat (`POST /api/v1/chat`) streams `tool_call`, `tool_result`, `card`, and `token` events;
  `card` events render as inline ECharts. Queries are scoped to the page being viewed
  (workflow/campaign/dashboard id is sent as context).

## Running

### Prerequisites

- Flowcept installed with the webservice extra (e.g., `pip install -e .[webservice]`, plus
  `[llm_agent]` for chat/agent and your DB extras such as `[mongo]`).
- Services up (e.g., `make services-mongo` for Redis + MongoDB).
- Node 22+ and npm only if you build or develop the UI yourself.

### Production-style (single server)

```bash
make ui-install   # once: npm ci
make ui-build     # builds into src/flowcept/webservice/ui_build
flowcept --start-webservice            # serves UI + API on web_server.host:port (default :5000)
# open http://localhost:5000           (REST docs at /docs)
```

If the built assets are missing, the webservice logs a warning and serves the API only.

### Development (hot reload)

```bash
# terminal 1 — API:
uvicorn flowcept.webservice.main:app --port 5000 --reload
# terminal 2 — UI dev server (proxies /api to :5000):
make ui-dev        # http://localhost:5173
```

Dev-server ports are configurable via env vars (override defaults without editing files):

| Variable | Default | Purpose |
|---|---|---|
| `WEBSERVER_HOST` | `0.0.0.0` | FastAPI bind host (Python, also honoured by `flowcept --start-webservice`) |
| `WEBSERVER_PORT` | `5000` | FastAPI bind port |
| `VITE_API_HOST` | `localhost` | API host the Vite proxy forwards `/api` requests to |
| `VITE_API_PORT` | `5000` | API port the Vite proxy forwards to |
| `VITE_DEV_PORT` | `5173` | Vite dev server listen port |

Example — API on a non-default port:
```bash
WEBSERVER_PORT=8080 uvicorn flowcept.webservice.main:app --port 8080 --reload
VITE_API_PORT=8080 make ui-dev
```

Type-check/build verification: `make ui-checks` / `make ui-build`.

### Enabling the chat (LLM)

The chat endpoint reuses the `agent` section of your Flowcept settings (`~/.flowcept/settings.yaml`
or `FLOWCEPT_SETTINGS_PATH`):

```yaml
agent:
  enabled: true
  service_provider: openai   # sambanova | azure | openai | google
  llm_server_url: <your endpoint, for openai-compatible servers>
  api_key: <key>
  model: <model name>
web_server:
  chat:
    enabled: true
    max_tool_iterations: 5
    max_query_limit: 1000
```

Without this, `POST /api/v1/chat` returns 503 and the rest of the UI works normally.
The LLM answers with real DB-backed tools (query tasks/workflows, task summaries, campaigns,
agents, chart building) — the same shared tool core used by the MCP agent
(`src/flowcept/agents/tools/prov_tools.py`).

### Running the MCP agent alongside

The MCP agent is a separate server for external agent clients (Claude Code, Codex, etc.) and
live in-memory analysis. It now also exposes the DB-backed provenance tools
(`query_provenance_tasks`, `list_provenance_campaigns`, ...):

```bash
flowcept --start-agent     # MCP (streamable HTTP) on agent.mcp_host:mcp_port (default :8000)
```

The web UI does not require the agent; the chat panel talks to the webservice directly.

## Tests

End-to-end integration tests (real services, no mocks) live in
`tests/webservice/test_webservice_integration.py` (REST, SSE, dashboards, prov cards, chat —
the LLM round-trip runs when `agent.api_key` is configured) and
`tests/agent/agent_tests.py` (MCP tools against a running agent).
