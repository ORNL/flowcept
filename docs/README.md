# Flowcept Docs: Workflow Developer Start Here

This is the easiest end-to-end guide for workflow developers.

- Docs site: https://flowcept.readthedocs.io/
- Swagger (when webservice is running): `http://127.0.0.1:8008/docs`
- OpenAPI (ReadTheDocs):
  - https://flowcept.readthedocs.io/en/latest/flowcept-openapi.json
  - https://flowcept.readthedocs.io/en/latest/flowcept-openapi.yaml

## TL;DR (copy/paste)

If you only want to see Flowcept working in 2 minutes:

```bash
pip install flowcept
flowcept --init-settings
python examples/start_here.py
```

Then inspect `flowcept_buffer.jsonl`.

## Choose Your Path

- I want local/offline only (no services): go to [Offline path](#offline-path-no-services)
- I want DB/API querying: go to [Online DB path](#online-db-path)
- I want natural-language querying with an agent: go to [Agentic path](#agentic-path)
- I want polished reports: go to [Provenance reports](#provenance-reports)

## Table of Contents

- [1) Install and setup](#1-install-and-setup)
- [2) Capture provenance](#2-capture-provenance)
  - [2.1 Simplest example](#21-simplest-example)
  - [2.2 Custom capture examples](#22-custom-capture-examples)
  - [2.3 Advanced capture](#23-advanced-capture)
- [3) Access captured provenance](#3-access-captured-provenance)
  - [Offline path (no services)](#offline-path-no-services)
  - [Online DB path](#online-db-path)
    - [Python Query API](#python-query-api)
    - [REST API](#rest-api)
    - [MQ subscribe](#mq-subscribe)
  - [Agentic path](#agentic-path)
    - [Use your own code assistant](#use-your-own-code-assistant)
    - [Internal-LLM mode](#internal-llm-mode)
  - [Grafana monitoring](#grafana-monitoring)
- [4) Provenance reports](#4-provenance-reports)
  - [Provenance cards (markdown)](#provenance-cards-markdown)
  - [Full reports (pdf)](#full-reports-pdf)
- [5) Architecture](#5-architecture)

## 1) Install and setup

Install base package:

```bash
pip install flowcept
```

Generate settings:

```bash
flowcept --init-settings
```

Full file vs runtime mode:

```bash
flowcept --init-settings --full -y
flowcept --config-profile full-online -y
```

Important: `settings.yaml` is the single source of truth for Flowcept runtime behavior.

- default path: `~/.flowcept/settings.yaml`
- override path env var: `FLOWCEPT_SETTINGS_PATH`

Settings reference:

- https://flowcept.readthedocs.io/en/latest/setup.html
- https://github.com/ORNL/flowcept/blob/main/resources/sample_settings.yaml

Quick config profiles (recommended):

```bash
flowcept --config-profile full-online
flowcept --config-profile full-telemetry
flowcept --config-profile mq-only
flowcept --config-profile full-offline
```

What this does:

- Shows exactly which `settings.yaml` keys will be changed and the new values.
- Asks for confirmation before writing.
- Writes to `FLOWCEPT_SETTINGS_PATH` when set, otherwise `~/.flowcept/settings.yaml`.

Skip confirmation:

```bash
flowcept --config-profile full-online -y
```

Current profile behavior:

- `full-online`:
  - `project.db_flush_mode: online`
  - `mq.enabled: true`
  - `kv_db.enabled: true`
  - `databases.mongodb.enabled: true`
  - `databases.lmdb.enabled: false`
- `mq-only`:
  - `project.db_flush_mode: online`
  - `mq.enabled: true`
  - `kv_db.enabled: false`
  - `databases.mongodb.enabled: false`
  - `databases.lmdb.enabled: false`
  - Use `Flowcept(check_safe_stops=False)` with this profile.
- `full-offline`:
  - `project.db_flush_mode: offline`
  - `project.dump_buffer.enabled: true`
  - `mq.enabled: false`
  - `kv_db.enabled: false`
  - `databases.mongodb.enabled: false`
  - `databases.lmdb.enabled: false`
- `full-telemetry`:
  - enables CPU, per-CPU, process, memory, disk, network, machine telemetry
  - keeps `telemetry_capture.gpu: null`

Adapter setup is additive:

```bash
flowcept --init-settings --dask -y
flowcept --init-settings --mlflow -y
flowcept --init-settings --tensorboard -y
```

These commands add `adapters.<name>` to the current settings file.

## 2) Capture provenance

### 2.1 Simplest example

Use:

- `examples/start_here.py`

Run:

```bash
python examples/start_here.py
```

Sample code (decorator-based, simplest path):

```python
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
    prov_buffer = Flowcept.read_buffer_file()
    print(json.dumps(prov_buffer, indent=2))
```

### 2.2 Custom capture examples

Use:

- `examples/unmanaged/simple_task2.py`
- `examples/unmanaged/simple_task.py`
- `examples/unmanaged/main.py`

These show explicit `FlowceptTask`, `.send()`, context manager, tags, and metadata.

Sample code (explicit task objects, no decorators):

```python
import uuid
from time import sleep

from flowcept import Flowcept, FlowceptTask

if __name__ == "__main__":
    agent1 = str(uuid.uuid4())

    flowcept = Flowcept(
        start_persistence=False,
        save_workflow=True,
        workflow_name="My First Workflow",
        campaign_id="my_super_campaign",
    ).start()

    # 1) direct event emission
    FlowceptTask(activity_id="super_func1", used={"x": 1}, agent_id=agent1, tags=["tag1"]).send()

    # 2) context-managed start/end
    with FlowceptTask(activity_id="super_func2", used={"y": 1}, agent_id=agent1, tags=["tag2"]) as t2:
        sleep(0.5)
        t2.end(generated={"o": 3})

    # 3) explicit start + explicit end
    t3 = FlowceptTask(activity_id="super_func3", used={"z": 1}, agent_id=agent1, tags=["tag3"])
    sleep(0.1)
    t3.end(generated={"w": 1})

    flowcept.stop()
```

### 2.3 Advanced capture

PyTorch + loops:

- docs: https://flowcept.readthedocs.io/en/latest/prov_capture.html
- example: `examples/single_layer_perceptron_example.py`
- loop example: `examples/instrumented_loop_example.py`
- tests:
  - `tests/instrumentation_tests/ml_tests/single_layer_perceptron_test.py`
  - `tests/instrumentation_tests/flowcept_loop_test.py`

Adapters:

- MLflow:
  - `examples/mlflow_example.py`
  - `notebooks/mlflow.ipynb`
  - `tests/adapters/test_mlflow.py`
- Dask:
  - `examples/dask_example.py`
  - `notebooks/dask.ipynb`
  - `tests/adapters/test_dask.py`
- TensorBoard:
  - `examples/tensorboard_example.py`
  - `notebooks/tensorboard.ipynb`
  - `tests/adapters/test_tensorboard.py`

Agentic provenance / MCP:

- docs: https://flowcept.readthedocs.io/en/latest/agent.html
- agent readme: `src/flowcept/agents/README.md`
- skills contract: `src/flowcept/agents/SKILLS.md`
- agent tests: `tests/agent/agent_tests.py`
- PROV-AGENT paper: https://arxiv.org/abs/2508.02866

## 3) Access captured provenance

### Offline path (no services)

Best for simple local runs and CI-lite usage.

Install:

```bash
pip install flowcept
```

Use this config:

```yaml
project:
  db_flush_mode: offline
  dump_buffer:
    enabled: true
    path: flowcept_buffer.jsonl
mq:
  enabled: false
kv_db:
  enabled: false
databases:
  mongodb:
    enabled: false
  lmdb:
    enabled: false
```

Read file via Flowcept:

```python
from flowcept import Flowcept

docs = Flowcept.read_buffer_file("flowcept_buffer.jsonl")
df = Flowcept.read_buffer_file("flowcept_buffer.jsonl", return_df=True, normalize_df=True)
```

Read file via pandas:

```python
import pandas as pd
df = pd.read_json("flowcept_buffer.jsonl", lines=True)
```

### Online DB path

Use this when you need workflow/task/object queries after execution.

Typical config requirements:

- `project.db_flush_mode: online`
- `mq.enabled: true`
- `kv_db.enabled: true`
- `databases.mongodb.enabled: true` (or LMDB mode)

#### Python Query API

Install:

```bash
pip install flowcept[mongo]
```

Examples:

```python
from flowcept import Flowcept

tasks = Flowcept.db.get_tasks_from_current_workflow()

failed = Flowcept.db.query(
    collection="tasks",
    filter={"status": "ERROR"},
    projection={"_id": 0, "task_id": 1, "activity_id": 1, "stderr": 1},
    limit=20,
)

wfs = Flowcept.db.workflow_query(filter={"name": "Perceptron GridSearch"})
objs = Flowcept.db.query(collection="objects", filter={"workflow_id": Flowcept.current_workflow_id})
```

More docs:

- https://flowcept.readthedocs.io/en/latest/prov_query.html
- https://flowcept.readthedocs.io/en/latest/api-reference.html

#### REST API

Install:

```bash
pip install flowcept[webservice,mongo]
```

Start webservice:

```bash
flowcept --start-webservice --webservice-host=127.0.0.1 --webservice-port=8008
```

Quick curl examples:

```bash
curl -s http://127.0.0.1:8008/api/v1/health/live
curl -s 'http://127.0.0.1:8008/api/v1/tasks?limit=5'
curl -s -X POST http://127.0.0.1:8008/api/v1/tasks/query \
  -H 'Content-Type: application/json' \
  -d '{"filter":{"status":"FINISHED"},"limit":5}'
```

Docs endpoints:

- Swagger: http://127.0.0.1:8008/docs
- ReDoc: http://127.0.0.1:8008/redoc
- OpenAPI JSON: http://127.0.0.1:8008/openapi.json
- ReadTheDocs REST docs: https://flowcept.readthedocs.io/en/latest/rest_api.html

#### MQ subscribe

Install:

```bash
pip install flowcept[redis]
```

CLI stream helper:

```bash
flowcept --stream-messages
flowcept --stream-messages --keys-to-show activity_id,workflow_id,status
```

Examples:

- `examples/consumers/simple_consumer.py`
- `examples/consumers/simple_publisher.py`
- `examples/consumers/ping_pong_example.py`

### Agentic path

Paper: https://arxiv.org/abs/2509.13978

Install:

```bash
pip install flowcept[llm_agent]
```

#### Use your own code assistant

Recommended for Codex/Claude/Gemini users.

1. Start MCP server in a separate terminal:

```bash
flowcept --start-agent
```

2. Configure external-LLM mode:

```yaml
agent:
  external_llm: true
  mcp_host: 127.0.0.1
  mcp_port: 8000
```

3. In your assistant session, load:

- `src/flowcept/agents/SKILLS.md`

Recommended flow: clone this repo and ask your assistant to read that file.

#### Internal-LLM mode

Flowcept builds the model using `build_llm_model()` (`src/flowcept/agents/agents_utils.py`).

Providers in code:

- `openai`
- `azure`
- `google`
- `sambanova`

Common settings under `agent`:

- `service_provider`
- `model`
- `model_kwargs`
- `api_key`
- `llm_server_url`
- `mcp_host`, `mcp_port`

Start agent UI:

```bash
flowcept --start-agent-gui
```

### Grafana monitoring

Deployment file:

- `deployment/compose-grafana.yml`

Use this for online telemetry dashboards and KPI correlations (for example loss vs CPU/GPU behavior).

Telemetry docs:

- https://flowcept.readthedocs.io/en/latest/telemetry_capture.html

## 4) Provenance reports

### Provenance cards (markdown)

Default report mode:

- `report_type="provenance_card"`
- `format="markdown"`

Python API:

```python
from flowcept import Flowcept

Flowcept.generate_report(
    report_type="provenance_card",
    format="markdown",
    workflow_id="<workflow_id>",
    output_path="PROVENANCE_CARD.md",
)
```

REST download:

```bash
curl -s -X POST \
  http://127.0.0.1:8008/api/v1/workflows/<workflow_id>/reports/provenance-card/download
```

Docs:

- https://flowcept.readthedocs.io/en/latest/reporting.html

### Full reports (pdf)

Install:

```bash
pip install flowcept[report_pdf]
```

Generate:

```python
from flowcept import Flowcept

Flowcept.generate_report(
    report_type="provenance_report",
    format="pdf",
    workflow_id="<workflow_id>",
    output_path="PROVENANCE_REPORT.pdf",
)
```

PDF report supports ML-specialized KPI plotting when signals are available.

## 5) Architecture

One-line architecture:

- capture (instrumentation/adapters) -> MQ -> DB/file -> query via Python/REST/agent -> report.

Read more:

- https://flowcept.readthedocs.io/en/latest/architecture.html
- https://flowcept.readthedocs.io/en/latest/prov_capture.html
- https://flowcept.readthedocs.io/en/latest/prov_storage.html
- https://flowcept.readthedocs.io/en/latest/prov_query.html
- https://flowcept.readthedocs.io/en/latest/agent.html

## Common failures and quick fixes

- Symptom: `flowcept: command not found`
  - Fix: activate your Python env first, then reinstall: `pip install flowcept`
- Symptom: no `flowcept_buffer.jsonl` after running offline example
  - Fix: ensure `project.db_flush_mode: offline` and `project.dump_buffer.enabled: true` in settings
- Symptom: `ValueError` about `db_flush_mode` vs MQ/DB settings
  - Fix: keep config consistent:
    - Offline mode: disable MQ/KV/DBs
    - Online mode: use `flowcept --config-profile full-online -y` or `flowcept --config-profile mq-only -y`
- Symptom: `ValueError` about `check_safe_stops=True` requiring KV while MQ is enabled
  - Fix: either use `flowcept --config-profile full-online -y`, or keep `mq-only` and instantiate `Flowcept(check_safe_stops=False)`
- Symptom: REST API import/start failures (`fastapi`/`uvicorn` missing)
  - Fix: `pip install flowcept[webservice,mongo]`
- Symptom: `Flowcept.db` queries fail due to missing Mongo deps
  - Fix: `pip install flowcept[mongo]`
- Symptom: agent won’t respond / cannot connect
  - Fix:
    - start server: `flowcept --start-agent`
    - confirm `agent.mcp_host`/`agent.mcp_port` in settings
    - in external assistant mode, load `src/flowcept/agents/SKILLS.md`
- Symptom: PDF report generation fails
  - Fix: install report deps: `pip install flowcept[report_pdf]`

## Command cheat sheet

```bash
# Install
pip install flowcept
pip install flowcept[mongo]
pip install flowcept[webservice,mongo]
pip install flowcept[llm_agent]
pip install flowcept[report_pdf]

# Init settings
flowcept --init-settings
flowcept --config-profile full-online
flowcept --config-profile mq-only
flowcept --config-profile full-offline
flowcept --show-settings

# Start services
flowcept --start-webservice --webservice-host=127.0.0.1 --webservice-port=8008
flowcept --start-agent
flowcept --start-agent-gui

# Stream MQ messages
flowcept --stream-messages
flowcept --stream-messages --keys-to-show activity_id,workflow_id,status

# Run simple example
python examples/start_here.py
```

```python
# Python quick calls
from flowcept import Flowcept

# Read offline buffer
docs = Flowcept.read_buffer_file("flowcept_buffer.jsonl")
df = Flowcept.read_buffer_file("flowcept_buffer.jsonl", return_df=True, normalize_df=True)

# Generate markdown provenance card
Flowcept.generate_report(
    report_type="provenance_card",
    format="markdown",
    workflow_id="<workflow_id>",
    output_path="PROVENANCE_CARD.md",
)

# Generate PDF provenance report
Flowcept.generate_report(
    report_type="provenance_report",
    format="pdf",
    workflow_id="<workflow_id>",
    output_path="PROVENANCE_REPORT.pdf",
)
```
