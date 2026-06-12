Web UI
======

Flowcept ships a built-in web interface for browsing and analyzing provenance data.
It is a React single-page application served directly by the Flowcept webservice — no
separate process or Node.js installation is needed by end users.

.. contents:: On this page
   :local:
   :depth: 2


Installation
------------

Install Flowcept with the ``webservice`` extra (the UI assets are bundled in the wheel):

.. code-block:: bash

   pip install flowcept[webservice]

For the LLM chat feature also add ``llm_agent`` and a model provider extra:

.. code-block:: bash

   pip install flowcept[webservice,llm_agent]


Prerequisites
~~~~~~~~~~~~~

* A running MongoDB instance (recommended; most UI features work without it but
  dashboards and provenance cards require Mongo).
* A running Redis instance (required for the instrumentation message queue).

Start both with Docker Compose:

.. code-block:: bash

   make services-mongo   # Redis + MongoDB


Starting the UI
---------------

.. code-block:: bash

   flowcept --start-ui

This command:

1. Kills any previously running webservice or Vite process on the configured ports.
2. Starts the Flowcept webservice in the background (FastAPI + bundled UI assets).
3. Starts the Vite development server in the foreground (hot-reload, proxies ``/api``
   to the webservice).

Press ``Ctrl+C`` to stop both.

The UI is served on ``http://localhost:8008`` by default.
The API is available at ``http://localhost:8008/api/v1`` (interactive docs at
``http://localhost:8008/docs``).

Settings
~~~~~~~~

Configure the webservice in ``~/.flowcept/settings.yaml``:

.. code-block:: yaml

   web_server:
     host: 0.0.0.0
     port: 8008
     ui_enabled: true

All host/port values can also be set via environment variables
(``WEBSERVER_HOST``, ``WEBSERVER_PORT``), which take precedence over the settings file.


Pages
-----

Overview (``/``)
   At-a-glance stats: campaign and workflow counts, latest activity, recent campaigns,
   and the eight most-recent named workflows with tasks.

Campaigns (``/campaigns``)
   Card grid of all campaigns (groups of related workflow runs sharing a ``campaign_id``).
   Each card links to the campaign detail page.

Campaign detail (``/campaigns/<id>``)
   Tabs: **Workflows** (list of member workflows), **Dashboard** (aggregated charts),
   **Workflow Card** (generated provenance report).

Workflows (``/workflows``)
   Sortable list of all named workflows that have at least one task.

Workflow detail (``/workflows/<id>``)
   Tabs:

   * **Tasks** — paginated, sortable task table; click a row to open the Task Inspector.
   * **Graph** — BFS-ranked DAG of task dependencies.
   * **Dataflow** — W3C PROV-style dataflow graph (yellow entities, blue activities).
   * **Telemetry** — per-task CPU/memory/disk/network time-series.
   * **Artifacts** — objects (ML models, datasets) saved during the workflow.
   * **Dashboard** — per-workflow charts (see :ref:`web-ui-dashboards`).
   * **Workflow Card** — downloadable Markdown/PDF provenance report.
   * **Raw** — full workflow JSON document.

Artifacts (``/objects``)
   Browse all saved objects filtered by type (all / ml_model / dataset).
   Shows total size per type and per-object sizes.

Dashboard configs (``/dashboards``)
   View and manage the chart configuration schemas that define which charts appear
   in every workflow's and campaign's Dashboard tab.

Agent (``/agents``)
   List of agent tasks (tasks tagged with an ``agent_id``).


.. _web-ui-dashboards:

Dashboards
----------

Each workflow and campaign has a **Dashboard** tab populated by chart configuration
schemas stored server-side (MongoDB ``dashboards`` collection, or JSON files when
Mongo is unavailable).

There are four schema types:

.. list-table::
   :header-rows: 1

   * - Type
     - Applies to
     - Matched by
   * - ``common_workflow``
     - Every workflow's Dashboard tab
     - —
   * - ``common_campaign``
     - Every campaign's Dashboard tab
     - —
   * - ``custom_workflow``
     - A specific workflow (by name)
     - ``target == workflow.name``
   * - ``custom_campaign``
     - A specific campaign
     - ``target == campaign_id``

Default chart schemas are seeded automatically from
``src/flowcept/webservice/ui_build/default_dashboard_configs.json`` the first time
the service runs with an empty ``dashboards`` collection.

**Chart data binding (``ChartData``):**

.. code-block:: text

   source    : "tasks" | "workflows" | "objects" | "collection_sizes"
   filter    : {}           # Mongo-style filter; ANDed with the dashboard context
   group_by  : string       # dot-path field (e.g. "activity_id", "telemetry_at_end.cpu.percent_all")
   metrics   : [{field, agg}]  # agg: count | avg | sum | min | max
   x / y     : string / string[]  # for scatter/line charts
   limit     : 1–5000

Each chart's filter is automatically scoped to the current workflow or campaign via the
dashboard **context** (``workflow_id`` or ``campaign_id``).

Charts with no data are **hidden by default** but remain accessible via the toggle pills
above the grid.

The ``collection_sizes`` source is a special virtual source that returns BSON byte
totals for the ``tasks``, ``objects``, and ``workflows`` collections for the current
workflow or campaign — useful for storage-at-a-glance charts.


Chat (LLM)
----------

The chat panel (center-bottom, always visible) connects to ``POST /api/v1/chat`` and
answers questions about the provenance data using DB-backed tools:

* query tasks / workflows / campaigns / agents
* get task summaries
* build and pin charts to the dashboard

Configure the LLM in ``~/.flowcept/settings.yaml``:

.. code-block:: yaml

   agent:
     enabled: true
     service_provider: openai       # sambanova | azure | openai | google
     llm_server_url: <endpoint>
     api_key: <key>
     model: <model name>
   web_server:
     chat:
       enabled: true
       max_tool_iterations: 5
       max_query_limit: 1000

Without this configuration, the chat panel displays a "chat unavailable" message and
the rest of the UI works normally.


MCP Agent
---------

The Flowcept MCP agent is a separate server for external agent clients
(Claude Code, Codex, etc.):

.. code-block:: bash

   flowcept --start-agent   # default port: 8000

The web UI does not depend on the agent; the chat panel talks to the webservice
directly. See :doc:`agent` for full MCP agent documentation.


Development
-----------

.. code-block:: bash

   make ui-install   # install Node dependencies (once)
   make ui-dev       # Vite dev server with hot reload on http://localhost:5173
                     # (proxies /api to the webservice on :8008)
   make ui-checks    # TypeScript strict type-check + ESLint
   make ui-build     # production build → src/flowcept/webservice/ui_build/

See ``ui/README.md`` in the repository for the full stack description, code layout,
and architecture notes.
