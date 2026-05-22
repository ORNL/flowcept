# Flowcept: Agent Navigation Guide

> Fast-read reference for AI agents working in this repo. Read top-to-bottom once; jump to sections as needed.

---

## What Flowcept Is

Flowcept is a **lightweight distributed workflow provenance system** (Python, requires ≥3.11). It intercepts running workflows — ML training, HPC jobs, Dask tasks, etc. — and captures task/workflow metadata (inputs, outputs, timing, telemetry, lineage) into a streaming hub, then persists it to MongoDB or LMDB or a local JSONL file.

Key design: **non-intrusive by default** (adapters wrap existing frameworks) but also supports explicit decorator instrumentation. Built for the Edge-Cloud-HPC continuum (Frontier HPC is a primary target).

Installed in the `flowcept` conda environment. Always use that env.

---

## Repo Layout

```
flowcept/
├── src/flowcept/               # All source code
│   ├── __init__.py             # Public API exports: Flowcept, flowcept_task, etc.
│   ├── configs.py              # All settings loading logic
│   ├── cli.py                  # CLI entry point (flowcept --...)
│   ├── agents/                 # MCP agent server + client
│   │   ├── flowcept_agent.py   # MCP server (run with: flowcept --start-agent)
│   │   ├── agent_client.py     # run_tool(), run_prompt() helpers
│   │   ├── flowcept_ctx_manager.py  # In-memory context for agent queries
│   │   ├── tools/              # MCP tool implementations
│   │   ├── llms/               # LLM wrappers
│   │   ├── prompts/            # Prompt templates
│   │   ├── README.md           # How to use agents with external LLM
│   │   └── SKILLS.md           # Operating contract for external LLM orchestrators
│   ├── analytics/              # Analytics helpers
│   ├── commons/                # Shared utilities, MQ consumers, DB interfaces
│   ├── flowcept_api/           # Python-facing DBAPI (query layer)
│   ├── flowceptor/             # Adapters (MLflow, Dask, TensorBoard, etc.)
│   ├── instrumentation/        # Decorators, loops, PyTorch hooks
│   │   └── flowcept_task.py    # @flowcept_task, FlowceptLoop, etc.
│   ├── report/                 # Provenance report generation (markdown + PDF)
│   │   └── service.py          # Entry point: Flowcept.generate_report(...)
│   └── webservice/             # FastAPI REST API (read-only, /api/v1)
│       ├── main.py             # App factory
│       ├── routers/            # workflows.py, tasks.py, objects.py, health.py
│       ├── deps.py             # DBAPI injection
│       └── docs/               # API_CONTRACT.md, ARCHITECTURE.md
├── tests/
│   ├── adapters/               # Dask, MLflow, TensorBoard adapter tests
│   ├── agent/                  # Agent tool tests
│   ├── api/                    # DBAPI + webservice tests
│   ├── instrumentation_tests/  # Decorator, loop, PyTorch tests
│   │   └── ml_tests/           # single_layer_perceptron_test.py (canonical ML test)
│   ├── report/                 # Report generation tests
│   └── webservice/             # FastAPI endpoint tests
├── examples/
│   ├── start_here.py           # Minimal decorator example
│   ├── single_layer_perceptron_example.py  # ML example with blob storage
│   ├── dask_example.py
│   ├── mlflow_example.py
│   ├── instrumented_loop_example.py
│   ├── convergence_loop_example.py
│   ├── agents/a2a/             # Agent-to-agent example
│   ├── llm_tutorial/           # Progressive provenance tutorial (LLM training)
│   └── llm_complex/            # Frontier/ROCm GPU example
├── docs/                       # Sphinx RST documentation
├── resources/
│   └── sample_settings.yaml   # Canonical settings template — always consult this
├── deployment/                 # Docker Compose, deployment configs (use ${DATA_DIR} placeholders)
├── agent_sandbox/              # Agent scratch space (this file lives here)
├── notebooks/                  # Jupyter notebooks
├── CLAUDE.md                   # Rules for Claude agents (MUST READ)
├── pyproject.toml              # Dependencies and extras
└── Makefile                    # Test targets
```

---

## Core Concepts

### Data Model Hierarchy
```
Campaign  (campaign_id)
  └── Workflow  (workflow_id)  ← one Python Flowcept() context = one workflow
        └── Task  (task_id)   ← one function call / loop iteration / adapter event
              └── Object      (object_id) ← blob (model checkpoint, dataset, artifact)
```

- **Task record**: type, subtype, task_id, workflow_id, activity_id, parent_task_id, agent_id, submitted_at/started_at/ended_at, used (inputs), generated (outputs), status, stdout, stderr, telemetry_at_start, telemetry_at_end, node_name, hostname, user, custom_metadata
- **Workflow record**: workflow_id, campaign_id, name, machine_info, conf, flowcept_version, user, environment_id
- **Object record**: object_id, version, task_id, workflow_id, type (ml_model | dataset | ...), data (binary), custom_metadata, prev_version (for version control)

### Two Capture Modes
1. **Adapters (non-intrusive)**: wrap existing frameworks — MLflow, Dask, TensorBoard — via `Flowcept(instrumentation_interceptors=["dask"])` or CLI `--dask`.
2. **Instrumentation (explicit)**: `@flowcept_task`, `@flowcept`, `FlowceptLoop`, `@flowcept_torch` decorators/hooks directly in code.

### Storage Backends
- **Message Queue**: Redis (default), Kafka, or Mofka — pub/sub streaming hub between producer and consumers.
- **MongoDB**: primary persistent store (DocumentInserter consumer writes to it).
- **LMDB**: embedded key-value alternative.
- **Offline JSONL buffer**: when `db_flush_mode: offline`, writes to a `.jsonl` file — no external services needed.

---

## Settings (Critical)

All runtime behavior is controlled by a YAML settings file. Never hardcode in Python.

**Location order**: `FLOWCEPT_SETTINGS_PATH` env var → `~/.flowcept/settings.yaml` → defaults.

**Canonical template**: `resources/sample_settings.yaml`

**Key sections**:
```yaml
project:
  db_flush_mode: offline        # "offline" = JSONL file, "online" = DB
  enrich_messages: true         # adds IP, timestamps, git metadata to tasks
  dump_buffer:
    enabled: true
    path: flowcept_buffer.jsonl

mq:                             # Message queue (Redis)
  enabled: true
  type: redis
  host: localhost
  port: 6379

kv_db:                          # Key-value DB (Redis)
  enabled: true
  host: localhost
  port: 6379

databases:
  mongodb:
    enabled: false
    host: localhost
    port: 27017
    db: flowcept
  lmdb:
    enabled: false

telemetry_capture:              # Leave empty {} to disable all; set keys to true to enable
  cpu: true
  gpu: true                     # AMD ROCm SMI or NVIDIA NVML
  memory: true
  disk: true
  network: true
  process_info: true

instrumentation:
  enabled: false
  torch:
    what: ~                     # parent_only | parent_and_children | ~
    children_mode: ~            # tensor_inspection | telemetry | telemetry_and_tensor_inspection
    epoch_loop: ~               # default | lightweight | ~
    batch_loop: ~               # default | lightweight | ~
    capture_epochs_at_every: 1
    register_workflow: false

agent:
  external_llm: true            # true = external LLM orchestrates; false = internal routing
  mcp_host: 127.0.0.1
  mcp_port: 8000
```

**CLI profiles** (bootstrap shortcuts):
```bash
flowcept --init-settings --config-profile full-online     # Redis + MongoDB
flowcept --init-settings --config-profile full-offline    # JSONL only
flowcept --init-settings --config-profile mq-only         # Redis, no DB persist
```

---

## Capture API Quick Reference

### Simplest possible (offline, no services required)
```python
from flowcept import Flowcept, flowcept_task

@flowcept_task
def my_func(x, y):
    return {"result": x + y}

with Flowcept():
    my_func(1, 2)

# Read buffer
import pandas as pd
df = Flowcept.read_messages_file("flowcept_buffer.jsonl", return_df=True)
```

### Decorators
```python
from flowcept.instrumentation.flowcept_task import flowcept_task, flowcept

@flowcept                          # marks function as a WORKFLOW
def my_pipeline(...): ...

@flowcept_task                     # marks function as a TASK
def my_step(...): ...

@flowcept_task(                    # with options
    args_handler=my_handler,       # transform args before capture
    output_names=["loss", "acc"],  # name the return tuple fields
)
def train(...): ...
```

### Context manager (explicit workflow boundary)
```python
with Flowcept(workflow_name="MyWorkflow", workflow_args={"lr": 0.01}) as fc:
    my_step()
    workflow_id = fc.current_workflow_id
```

### Manual start/stop
```python
fc = Flowcept()
fc.start()
# ... work ...
fc.stop()
```

### Distributed (share workflow_id across processes)
```python
# Flowcept auto-generates a workflow_id (uuid4) when none is passed.
# Access it via fc.current_workflow_id after the context opens.
with Flowcept(workflow_name="MyWF") as fc:
    wf_id = fc.current_workflow_id  # broadcast this to worker processes

# Worker processes: start_persistence=False lets the standalone consumer
# handle DB writes. check_safe_stops=False when kv_db.enabled=False.
with Flowcept(workflow_id=wf_id, start_persistence=False, check_safe_stops=False):
    my_task()
```

### Adapters
```python
Flowcept(instrumentation_interceptors=["dask"])   # or "mlflow", "tensorboard"
```

### Loop instrumentation
```python
from flowcept.instrumentation.flowcept_task import FlowceptLoop, FlowceptLightweightLoop

for i in FlowceptLoop(range(100), workflow_id=wf_id):
    ...

for i in FlowceptLightweightLoop(range(100)):
    ...
```

### PyTorch model instrumentation
```python
from flowcept.instrumentation.flowcept_task import flowcept_torch

@flowcept_torch
class MyModel(nn.Module): ...
```

### Custom task creation (manual)
```python
from flowcept.instrumentation.flowcept_task import FlowceptTask

task = FlowceptTask(workflow_id=wf_id)
task.begin()
# ... work ...
task.end({"output_key": value})
```

### Get current task id (inside an instrumented function)
```python
from flowcept.instrumentation.flowcept_task import get_current_context_task_id
task_id = get_current_context_task_id()
```

---

## Query API Quick Reference

### Python (requires MongoDB or LMDB running)
```python
tasks = Flowcept.db.task_query(filter={"workflow_id": wf_id})
workflows = Flowcept.db.workflow_query(filter={"name": "MyWorkflow"})
```

### From offline JSONL file
```python
df = Flowcept.read_messages_file("flowcept_buffer.jsonl", return_df=True)
# filter: df[df["type"] == "task"]
```

### CLI
```bash
flowcept --workflow-count
flowcept --query --filter '{"workflow_id": "abc123"}'
flowcept --get-task --task-id "xyz"
```

### REST API (webservice must be running)
```bash
uvicorn flowcept.webservice.main:app --host 0.0.0.0 --port 5000
# then:
GET  /api/v1/tasks?workflow_id=abc123
POST /api/v1/tasks/query  body: {"filter": {...}, "limit": 100}
GET  /api/v1/workflows/{workflow_id}
POST /api/v1/workflows/{workflow_id}/reports/provenance-card/download
```
Swagger UI: `http://localhost:5000/docs`

---

## Blob (Object) Storage API

Store model checkpoints, datasets, or any binary artifact linked to a task/workflow.

```python
# Save dataset (pickle, version-controlled)
obj_id = Flowcept.db.save_or_update_dataset(
    object={"x": x_train, "y": y_train},
    task_id=get_current_context_task_id(),
    custom_metadata={"n_samples": 120},
    save_data_in_collection=True,
    pickle=True,
    control_version=True,
)

# Save ML model (generic, format-agnostic)
obj_id = Flowcept.db.save_or_update_ml_model(
    object=model.state_dict(),
    object_id=obj_id,           # reuse to create new version
    task_id=task_id,
    pickle=True,
    control_version=True,
)

# Save PyTorch model (convenience)
obj_id = Flowcept.db.save_or_update_torch_model(
    model=model, object_id=obj_id, task_id=task_id, control_version=True
)

# Load
blob = Flowcept.db.get_ml_model(obj_id)
model.load_state_dict(pickle.loads(blob.data))

Flowcept.db.load_torch_model(model, obj_id)
```

---

## Reporting

```python
# Markdown provenance card (default)
Flowcept.generate_report(workflow_id=wf_id, output_path="card.md")

# From JSONL buffer
Flowcept.generate_report(input_jsonl_path="buffer.jsonl")

# For a whole campaign
Flowcept.generate_report(campaign_id=campaign_id)

# PDF (needs matplotlib + reportlab)
Flowcept.generate_report(workflow_id=wf_id, report_type="provenance_report", format="pdf", output_path="report.pdf")
```

CLI:
```bash
flowcept generate_report buffer.jsonl
flowcept generate_report buffer.jsonl --format pdf
```

---

## Agent / MCP Interface

The MCP server exposes Flowcept as tools for LLM orchestrators (Claude Code, Codex, etc.).

### Start agent server
```bash
FLOWCEPT_SETTINGS_PATH=agent_sandbox/codex_tests_settings.yaml flowcept --start-agent
# or
python -m flowcept.agents.flowcept_agent
```

### Minimal settings for agent mode (save to `agent_sandbox/codex_tests_settings.yaml`)
```yaml
project:
  db_flush_mode: online
log:
  log_file_level: disable
  log_stream_level: disable
telemetry_capture: {}
mq:
  enabled: true
  type: redis
  host: localhost
  port: 6379
kv_db:
  enabled: true
  host: localhost
  port: 6379
databases:
  mongodb:
    enabled: false
  lmdb:
    enabled: false
agent:
  external_llm: true
  mcp_host: 127.0.0.1
  mcp_port: 8000
```

### Client usage
```python
from flowcept.agents.agent_client import run_tool, run_prompt

run_tool("check_liveness", host="127.0.0.1", port=8000)
run_tool("get_latest", host="127.0.0.1", port=8000)

# External LLM query flow (3-step):
prompt = run_prompt("build_df_query_prompt", args={"query": "top 5 slowest tasks"}, host="127.0.0.1", port=8000)
# LLM generates: generated_code = "result = df.nlargest(5, 'elapsed_sec')"
run_tool("execute_generated_df_code", kwargs={"user_code": generated_code}, host="127.0.0.1", port=8000)
```

CLI agent client:
```bash
flowcept --agent-client --tool-name check_liveness
flowcept --agent-client --tool-name prompt_handler --kwargs '{"message": "result = df.head()"}'
```

**Key agent tools**: `check_liveness`, `get_latest`, `prompt_handler`, `run_df_query`, `execute_generated_df_code`, `record_guidance`, `reset_context`, `generate_workflow_provenance_card`

**`q:` shortcut**: In SKILLS.md mode, `q: <question>` auto-runs the 3-step external LLM query flow.

---

## Testing

```bash
# Run all tests (uses Makefile targets)
make test

# Run specific test file
conda run -n flowcept python -m pytest tests/instrumentation_tests/ml_tests/single_layer_perceptron_test.py -v

# Canonical ML test (covers blob storage, decorators, checkpointing, reports)
tests/instrumentation_tests/ml_tests/single_layer_perceptron_test.py
```

**TDD rule**: always check/extend existing tests before writing new ones. Prefer real LLMs and real data over mocks.

---

## CLAUDE.md Rules (Always Obey)

- Responses ≤50 words; warn before long operations.
- Use `conda env flowcept` for Python.
- `agent_sandbox/` is scratch space — use freely for tmp files, plans, context.
- Never `pip install`; report missing packages and give install command.
- No hardcoded absolute paths in committed code; use `${DATA_DIR}` in deployment templates.
- Prefer `settings.yaml` over hardcoded Python for any tunable behavior.
- No code duplication; reuse existing APIs.
- No fallback/backward-compat mechanisms — fail loudly.
- Git: always `git add file1 file2 ...` (never `git add -A`).
- Never stage `CLAUDE.md`.
- Test before suggesting commit; never auto-commit.
- Code style: early returns, flat structure, minimal indentation.

---

## HPC / OLCF Frontier

### Architecture (multi-node MPI, no MongoDB)
- Redis runs on the head rank's node; all ranks publish to it via `MQ_HOST=$(hostname)`.
- A standalone consumer (`flowcept --start-consumption-services`) reads from Redis and writes to LMDB.
- All ranks use `start_persistence=False, check_safe_stops=False` — consumer owns DB writes.
- Rank 0 creates the Flowcept context, gets `workflow_id`, broadcasts it via `comm.bcast`.

### LMDB path lookup
Scripts print `LMDB path: $LMDB_PATH` at startup — capture that value.
- Login-node: `flowcept_output/lmdb/<YYYYMMDD_HHMMSS>`
- Slurm: `flowcept_output/lmdb/<SLURM_JOB_ID>`

Do **not** use `ls -lt` to find the latest dir — regenerating reports updates mtimes. Query retroactively:
```python
import os; from pathlib import Path
os.environ['FLOWCEPT_SETTINGS_PATH'] = 'flowcept_settings.yaml'
for d in sorted(Path('flowcept_output/lmdb').iterdir()):
    if not (d / 'data.mdb').exists(): continue
    os.environ['LMDB_PATH'] = str(d)
    from flowcept import Flowcept
    if Flowcept.db.query(filter={'workflow_id': wf_id}, collection='tasks'):
        print(f'Found in: {d}'); break
```

### GPU telemetry keys (AMD MI250X)
All supported values for `telemetry_capture.gpu`:
- `used` — VRAM used (bytes)
- `activity` — GFX/UMC/MM engine utilization % (AMD only)
- `power` — average_socket_power (W) + energy_accumulator (AMD only)
- `temperature` — edge/hotspot/mem/vrgfx/vrmem/hbm (°C) + fan_speed (AMD only)
- `others` — current GFX/SOC/mem/video clocks MHz (AMD only)
- `id` — GPU UUID
- `name` — device name (NVIDIA only)

Requires: `pip install flowcept[amd]`, `LD_LIBRARY_PATH=/opt/rocm-X.Y.Z/lib`.

### Buffer tuning
```yaml
mq:
  buffer_size: 500               # records per Redis publish (default: 1)
  insertion_buffer_time_secs: 5  # force-flush interval (default: 1)
db_buffer:
  buffer_size: 500               # records per LMDB write transaction (default: 50)
  insertion_buffer_time_secs: 5
```

### Reporting from LMDB
```python
Flowcept.generate_report(report_type="provenance_card", format="markdown",
    workflow_id=wf_id, output_path="card.md")
Flowcept.generate_report(report_type="provenance_report", format="pdf",
    workflow_id=wf_id, output_path="report.pdf")
Flowcept.db.dump_to_file(collection="tasks", filter={"workflow_id": wf_id},
    output_file="tasks.parquet", export_format="parquet", should_zip=False)
```

---

## Common Failure Fixes

| Symptom | Fix |
|---|---|
| `FLOWCEPT_SETTINGS_PATH` not set | Export env var or pass `--settings` flag |
| MQ connection refused | Start Redis: `docker-compose up redis` or check `resources/` for compose files |
| No data in buffer file | Check `dump_buffer.enabled: true` and `dump_buffer.path` in settings |
| Agent not responding | Run `flowcept --start-agent` in a separate terminal first |
| `run_tool(...)` TypeError | Pass tool args via `kwargs={}` dict, not as top-level kwargs |
| Missing telemetry | Add telemetry keys under `telemetry_capture:` in settings |
| Tests failing on imports | Activate `conda env flowcept` before running |
| Wrong LMDB for a workflow_id | Query each dir via Flowcept API — don't rely on `ls -lt` |

---

## Key File Pointers

| What | Where |
|---|---|
| Public API | `src/flowcept/__init__.py` |
| All settings/config | `src/flowcept/configs.py` + `resources/sample_settings.yaml` |
| Task decorator impl | `src/flowcept/instrumentation/flowcept_task.py` |
| Adapters (Dask, MLflow…) | `src/flowcept/flowceptor/` |
| DB query API | `src/flowcept/flowcept_api/` |
| MCP agent server | `src/flowcept/agents/flowcept_agent.py` |
| Agent tools | `src/flowcept/agents/tools/` |
| REST API routes | `src/flowcept/webservice/routers/` |
| Report pipeline | `src/flowcept/report/service.py` |
| Canonical ML test | `tests/instrumentation_tests/ml_tests/single_layer_perceptron_test.py` |
| Example: start here | `examples/start_here.py` |
| Example: full ML | `examples/single_layer_perceptron_example.py` |
| Agent skills contract | `src/flowcept/agents/SKILLS.md` |
