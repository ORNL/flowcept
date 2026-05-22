# Flowcept Skills — Code Assistant Guide

This guide teaches a code assistant how to instrument code with Flowcept, query provenance data, and interact with the provenance agent. Read the whole guide before acting — the right approach depends on the use case.

---

## 0. Instrumentation Philosophy

Before writing any instrumentation, reason through two competing concerns:

**Intrusiveness** — how much does the instrumentation change the user's code? Adding `@flowcept_task` to an existing function is nearly zero-intrusion. Wrapping every line in `FlowceptTask` objects is high-intrusion.

**Provenance richness** — how much useful data does the instrumentation capture? Rich provenance enables queries like "which hyperparameters produced the best loss?" or "what was the input to the failing task?". Sparse provenance answers nothing.

**The goal is to find the minimum instrumentation that answers the queries the user cares about — not to capture everything.** Every provenance call has overhead (serialization, buffering, MQ I/O). In tight loops or parallel blocks this compounds fast and becomes a real performance bottleneck. Instrument coarsely by default; add finer granularity only when the query requires it.

Ask yourself:
- What questions will the user want to ask later? (What inputs caused this result? Which run was fastest? What did this task produce?)
- Which functions are the natural units of work — the tasks worth tracking?
- Can I get the needed provenance by decorating 2 functions instead of rewriting 10?

**Default recommendation:**
- Use `@flowcept_task` first — it is the cleanest, least intrusive, and handles the common case well.
- Switch to `FlowceptTask` when you need fields that the decorator cannot set (`agent_id`, `parent_task_id`, `subtype`, dynamic `activity_id`, custom `task_id`) or when the code cannot be decorated (third-party, generated, async with complex control flow).
- `FlowceptTask` gives the most control and customization of any approach — prefer it when provenance richness matters more than code cleanliness.
- Never instrument more than the user asked for. A few well-chosen tasks beat dozens of low-value ones.

---

## 1. Choosing the Right Instrumentation

| Situation | Best approach |
|-----------|---------------|
| Single function, cleanest code | `@flowcept_task` decorator |
| Entry-point function wrapping a workflow | `@flowcept` decorator |
| Code spanning multiple functions / files | `with Flowcept():` context manager |
| Need full control: custom fields, dynamic names, rich metadata | `FlowceptTask` (most powerful) |
| For/while loop with per-iteration capture | `FlowceptLoop` |
| PyTorch model (nn.Module) | `@flowcept_torch` |
| Dask distributed workflow | `FlowceptDaskWorkerAdapter` plugin |
| MLflow runs | `Flowcept("mlflow")` adapter |
| TensorBoard events | `Flowcept("tensorboard")` adapter |
| LLM / agentic tasks | `@agent_flowcept_task` |

---

## 2. Instrumentation Approaches

### 2.1 `@flowcept_task` — decorate a function

Captures function name as `activity_id`, arguments as `used`, return value as `generated`, plus timing and status.

```python
from flowcept import Flowcept, flowcept_task

@flowcept_task
def add(x, y):
    return x + y

@flowcept_task(output_names=["loss", "accuracy"])
def evaluate(model, data):
    return 0.05, 0.97

with Flowcept():
    add(1, 2)
    evaluate(model, val_data)
```

**Key parameters:**
- `output_names` (str or list): names for return values
- `custom_metadata` (dict): extra fields attached to every task record
- `tags` (list): semantic labels
- `subtype` (str): task category

**Variants for performance-sensitive code:**
- `@telemetry_flowcept_task`: same as above but captures hardware telemetry before/after
- `@lightweight_flowcept_task`: minimum overhead for HPC hot paths

---

### 2.2 `@flowcept` — decorate the workflow entry point

Wraps a function in a `Flowcept()` context. All `@flowcept_task` calls inside share the same `workflow_id`.

```python
from flowcept.instrumentation.flowcept_decorator import flowcept
from flowcept import flowcept_task

@flowcept_task(output_names="result")
def step(x):
    return x * 2

@flowcept(campaign_id="exp_1", workflow_name="My Pipeline")
def run():
    step(3)
    step(6)

run()
buffer = Flowcept.read_buffer_file()
```

Use this when the workflow is a single top-level function. Prefer `with Flowcept()` when the workflow spans several functions or needs dynamic control.

---

### 2.3 `with Flowcept()` — context manager

Most flexible. Use when the workflow is not neatly wrapped in one function.

```python
from flowcept import Flowcept, flowcept_task

@flowcept_task
def fetch(source):
    return load(source)

@flowcept_task
def transform(data):
    return process(data)

with Flowcept(workflow_name="etl", campaign_id="batch_42"):
    data = fetch("db://table")
    result = transform(data)
```

**Constructor parameters:**
- `interceptors` (str or list): adapter names (`"dask"`, `"mlflow"`, `"tensorboard"`)
- `workflow_id`, `campaign_id`, `workflow_name`, `workflow_subtype`, `workflow_args`
- `start_persistence` (bool, default True): publish to MQ
- `save_workflow` (bool, default True): emit workflow metadata message

---

### 2.4 `FlowceptTask` — full control and customization (most powerful)

`FlowceptTask` is the most expressive instrumentation primitive. Use it when:
- You need fields the decorator cannot set: `agent_id`, `parent_task_id`, `subtype`, `adapter_id`, `data`, or a dynamic `activity_id`
- The function cannot be decorated (third-party library, generated code, subprocess boundary)
- You want to emit tasks that don't map 1:1 to a function call
- You need the richest possible provenance and code cleanliness is a secondary concern

The decorator (`@flowcept_task`) is cleaner-looking and lower-intrusion for simple cases. When in doubt about which to use, ask: does the decorator capture everything needed for the queries the user will run? If yes, use the decorator. If no, use `FlowceptTask`.

**Performance warning:** Every provenance call — decorator or `FlowceptTask` — has overhead: serialization, buffering, possibly MQ I/O. In tight loops or parallel blocks (threads, multiprocessing, Dask workers), this overhead compounds and can become a performance bottleneck. Rules of thumb:
- Do not instrument every iteration of a hot loop. Use `FlowceptLoop` for coarse-grained loop provenance, or instrument only the outer call.
- In parallel code, each worker emitting its own provenance calls multiplies the overhead. Prefer capturing aggregate results at the join point rather than per-task inside the parallel block.
- If a function is called thousands of times per second, do not decorate it. Instrument one level up.
- When in doubt, measure: run with and without instrumentation and compare wall time.

```python
from flowcept import Flowcept, FlowceptTask

Flowcept().start()

# One-shot emission
FlowceptTask(
    activity_id="fetch_data",
    used={"source": "s3://bucket/file"},
    generated={"rows": 1000}
).send()

# Context manager — captures timing automatically
with FlowceptTask(activity_id="transform", used={"batch": 1}) as task:
    result = do_work()
    task.end(generated={"output_records": len(result)})

Flowcept().stop()
```

**All available fields:**
`task_id`, `workflow_id`, `campaign_id`, `activity_id`, `agent_id`, `source_agent_id`, `parent_task_id`, `used`, `generated`, `data`, `subtype`, `hostname`, `tags`, `adapter_id`, `custom_metadata`, `started_at`, `ended_at`, `stdout`, `stderr`, `status`

`.end(generated, ended_at, stderr, stdout, status)` — finalize with outputs.  
`.send()` — emit pre-populated task.

---

### 2.5 `FlowceptLoop` — instrument a loop

Captures each iteration as a separate task. Must call `loop.end_iter(dict)` at the end of every iteration body.

```python
from flowcept import Flowcept, FlowceptLoop

with Flowcept():
    loop = FlowceptLoop(range(10), loop_name="training", item_name="epoch")
    for epoch in loop:
        loss = train_one_epoch(epoch)
        loop.end_iter({"epoch": epoch, "loss": loss})
```

**Constructor:** `FlowceptLoop(items, loop_name, item_name, parent_task_id, workflow_id, items_length, capture_enabled)`

Works with any iterable; pass `items_length` for iterators without `len()`.

---

### 2.6 `@flowcept_torch` — PyTorch nn.Module

Instrument a model class. Each forward pass becomes a provenance task.

```python
from flowcept import Flowcept
from flowcept.instrumentation.flowcept_torch import flowcept_torch
import torch.nn as nn

@flowcept_torch
class MyNet(nn.Module):
    def __init__(self, **kwargs):
        super().__init__()
        self.fc = nn.Linear(10, 1)

    def forward(self, x):
        return self.fc(x)

with Flowcept():
    model = MyNet(get_profile=True)
    output = model(x)
```

**`__init__` extra kwargs:** `get_profile`, `custom_metadata`, `parent_task_id`, `parent_workflow_id`, `campaign_id`, `save_workflow`

Enable child-layer capture in `settings.yaml`:
```yaml
instrumentation:
  enabled: true
  torch:
    what: parent_and_children
    children_mode: lightweight   # or telemetry, tensor_inspection
    capture_epochs_at_every: 1
```

---

### 2.7 Dask adapter

Register the worker plugin on the client before submitting tasks.

```python
from distributed import Client, LocalCluster
from flowcept import Flowcept, FlowceptDaskWorkerAdapter

cluster = LocalCluster(n_workers=2)
client = Client(cluster.scheduler.address)
client.register_plugin(FlowceptDaskWorkerAdapter())

with Flowcept("dask"):
    future = client.submit(my_func, arg1, arg2)
    result = future.result()
```

Requires `adapters.dask` in `settings.yaml` (generated by `flowcept --init-settings --dask -y`).

---

### 2.8 MLflow adapter

Start `Flowcept("mlflow")` before your MLflow runs. Flowcept observes the SQLite/DB file and emits a task per run.

```python
import mlflow
from flowcept import Flowcept

with Flowcept("mlflow"):
    with mlflow.start_run():
        mlflow.log_param("lr", 0.01)
        mlflow.log_metric("loss", 0.05)
```

Requires `adapters.mlflow` in `settings.yaml`.

---

## 3. Offline vs Online Mode

| Mode | Services needed | Query method | Best for |
|------|----------------|--------------|---------|
| Offline | None | `read_buffer_file()` | local dev, CI, HPC |
| MQ only | Redis | `Flowcept.db` (transient) | real-time streaming |
| Full online (MongoDB) | Redis + MongoDB | `Flowcept.db` (persistent) | production, analysis |

**Offline settings** (default from `flowcept --init-settings -y`):
```yaml
project:
  db_flush_mode: offline
  dump_buffer:
    enabled: true
    path: flowcept_buffer.jsonl
mq:
  enabled: false
databases:
  mongodb:
    enabled: false
```

**Full online settings** (from `flowcept --init-settings --full -y`):
```yaml
project:
  db_flush_mode: online
mq:
  enabled: true
databases:
  mongodb:
    enabled: true
```

---

## 4. Querying Provenance

### 4.1 Read JSONL buffer (offline)

```python
from flowcept import Flowcept

records = Flowcept.read_buffer_file()                     # list of dicts
df      = Flowcept.read_buffer_file(return_df=True,
                                    normalize_df=True)     # pandas DataFrame
```

### 4.2 Query database (online)

```python
from flowcept import Flowcept

# Tasks from current workflow
tasks = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})

# Specific activity, sorted by time
tasks = Flowcept.db.task_query(
    filter={"activity_id": "train"},
    sort=[("started_at", -1)],
    limit=10
)

# Workflows in a campaign
wfs = Flowcept.db.workflow_query(filter={"campaign_id": my_campaign_id})

# As pandas DataFrame
df = Flowcept.db.to_df(filter={"workflow_id": wf_id})
df["elapsed"] = df["ended_at"] - df["started_at"]

# Aggregation pipeline
Flowcept.db.query(aggregation=[
    {"$group": {"_id": "$activity_id", "avg_elapsed": {"$avg": "$elapsed"}}}
])
```

### 4.3 Artifact objects

```python
Flowcept.db.get_ml_model("model_id")          # latest version
Flowcept.db.get_ml_model("model_id", version=3)
Flowcept.db.ml_model_query(filter={...})
Flowcept.db.dataset_query(filter={...})
Flowcept.db.list_object_versions("object_id")
```

### 4.4 In-memory buffer

```python
with Flowcept() as fc:
    run_tasks()
    df = fc.get_buffer(return_df=True)
```

---

## 5. Provenance Reports

```python
from flowcept import Flowcept

# From JSONL
Flowcept.generate_report(
    input_jsonl_path="flowcept_buffer.jsonl",
    format="markdown",
    print_markdown=True,
    output_path="prov_card.md"
)

# From in-memory records
records = Flowcept.read_buffer_file()
Flowcept.generate_report(records=records, format="markdown", print_markdown=True)

# From database by workflow
Flowcept.generate_report(workflow_id=wf_id, format="pdf", output_path="report.pdf")
```

Reports include: workflow summary, timing table, ASCII DAG, per-activity inputs/outputs, telemetry if captured.

---

## 6. Talking to the Provenance Agent

The agent is an MCP server. When you (a code assistant / external LLM) interact with it, always use **external LLM mode**. In this mode the agent is a context + tools backend — you do the reasoning, it executes. Do not rely on the agent's internal LLM routing or `prompt_handler` free-form dispatch.

Full contract: `src/flowcept/agents/README.md`.

### 6.1 Setup

**Step 1 — enable external LLM mode in settings:**
```yaml
agent:
  external_llm: true
```

**Step 2 — start the agent** (requires Redis running, run from the Flowcept conda env):
```bash
flowcept --start-agent
```

Transport is HTTP (`streamable-http`). The agent listens at `http://<host>:<port>/mcp`.

### 6.2 Explicit tool commands (use these)

Always prefer deterministic explicit commands over free-form natural language:

| Tool | Purpose |
|------|---------|
| `check_liveness` | Verify agent is up |
| `get_latest` | Fetch latest tasks/workflows into agent context |
| `reset_context` | Clear stale context; do this if results look wrong |
| `record_guidance` | Store guidance/memory in the agent |
| `show_records` | Display stored guidance |
| `reset_records` | Clear guidance |
| `build_df_query_prompt` | Get a prompt to generate a pandas query (see §6.3) |
| `execute_generated_df_code` | Execute pandas code in agent context |
| `generate_workflow_provenance_card` | Generate markdown report for a workflow |

### 6.3 DataFrame querying — external LLM flow

This is the expected sequence when a code assistant answers questions about provenance data:

**Step 1 — call the prompt builder:**
```python
from flowcept.agents.agent_client import run_prompt, run_tool

prompt_payload = run_prompt(
    "build_df_query_prompt",
    args={"query": "What are the top 5 slowest activities?"},
    host="127.0.0.1",
    port=8000,
)
```

**Step 2 — you (the external LLM) read the prompt and generate explicit pandas code:**
The prompt tells you the DataFrame schema and constraints. Generate code that assigns the result to `result`:
```python
generated_code = (
    "result = df.assign(elapsed=(df['ended_at'] - df['started_at']))"
    ".groupby('activity_id')['elapsed']"
    ".mean().sort_values(ascending=False).head(5)"
    ".reset_index(name='avg_elapsed_sec')"
)
```

**Step 3 — execute the generated code in agent context:**
```python
result = run_tool(
    "execute_generated_df_code",
    kwargs={"user_code": generated_code},
    host="127.0.0.1",
    port=8000,
)
print(result)
```

### 6.4 Other common calls

```python
# Check liveness
run_tool("check_liveness", host="127.0.0.1", port=8000)

# Load latest data into agent context (do this before querying)
run_tool("get_latest", host="127.0.0.1", port=8000)

# Recover from stale/noisy context
run_tool("reset_context", host="127.0.0.1", port=8000)

# Markdown provenance report for a workflow
run_tool("generate_workflow_provenance_card",
         kwargs={"workflow_id": wf_id},
         host="127.0.0.1", port=8000)
```

### 6.5 From CLI
```bash
flowcept --agent-client --tool-name check_liveness
flowcept --agent-client --tool-name get_latest
flowcept --agent-client --tool-name execute_generated_df_code \
  --kwargs '{"user_code":"result = df.head()"}'
```

### 6.6 If context drifts

If results look stale or inconsistent:
1. Call `reset_context`
2. Call `get_latest`
3. Re-run your query from a clean state

---

## 7. Key Concepts

| Concept | Meaning | Auto-generated? |
|---------|---------|-----------------|
| `workflow_id` | Groups all tasks in one run | Yes (UUID) |
| `campaign_id` | Groups multiple workflows (experiment) | Yes (UUID) |
| `task_id` | Identifies one task execution | Yes (timestamp-based) |
| `activity_id` | Human-readable task name | From function name or explicit |
| `used` | Inputs/resources consumed | From function args or explicit |
| `generated` | Outputs/resources produced | From return value or explicit |
| `status` | `FINISHED` or `ERROR` | Automatic |
| `started_at` / `ended_at` | Timestamps (epoch seconds) | Automatic |

**Access current context:**
```python
Flowcept.current_workflow_id
Flowcept.campaign_id
```

---

## 8. Complete Example (Offline)

```python
from flowcept import Flowcept, flowcept_task, FlowceptLoop
from flowcept.instrumentation.flowcept_decorator import flowcept

@flowcept_task(output_names="normalized")
def preprocess(raw):
    return [x / max(raw) for x in raw]

@flowcept_task(output_names="predictions")
def predict(data):
    return [x * 2 for x in data]

@flowcept(campaign_id="demo", workflow_name="pipeline")
def main():
    norm = preprocess([1, 2, 3, 4, 5])
    preds = predict(norm)

    loop = FlowceptLoop(preds, loop_name="eval", item_name="pred")
    for p in loop:
        loop.end_iter({"pred": p, "valid": p > 0})

main()

records = Flowcept.read_buffer_file()
print(f"Captured {len(records)} records")
Flowcept.generate_report(records=records, format="markdown", print_markdown=True)
```

---

## 9. Settings File Setup

### 9.1 Where Flowcept looks for settings

Flowcept resolves its settings file in this order:
1. `$FLOWCEPT_SETTINGS_PATH` environment variable (if set)
2. `~/.flowcept/settings.yaml` (default)

**Always prefer `FLOWCEPT_SETTINGS_PATH` when helping a user** — it keeps the user's project settings isolated from their global `~/.flowcept/settings.yaml` and avoids polluting other projects.

### 9.2 Creating a project-local settings file

Pick a path inside the project directory (e.g. `.flowcept/settings.yaml`) and set the env var before running any `flowcept` CLI commands or Python code:

```bash
# Set once in the shell (or add to .env / shell profile)
export FLOWCEPT_SETTINGS_PATH="$(pwd)/.flowcept/settings.yaml"

# Create minimal offline settings
flowcept --init-settings -y

# Or full online settings (Redis + MongoDB, instrumentation enabled)
flowcept --init-settings --full -y
```

From Python, set the env var before importing Flowcept:
```python
import os
os.environ["FLOWCEPT_SETTINGS_PATH"] = "/path/to/project/.flowcept/settings.yaml"

from flowcept import Flowcept  # picks up the env var
```

Or export it in the shell before running the script:
```bash
FLOWCEPT_SETTINGS_PATH=/path/to/project/.flowcept/settings.yaml python my_script.py
```

### 9.3 Choosing the right starting point

| Need | Command |
|------|---------|
| No external services (local dev, CI) | `flowcept --init-settings -y` |
| Full online: Redis + MongoDB + instrumentation | `flowcept --init-settings --full -y` |
| Add Dask adapter to existing file | `flowcept --init-settings --dask -y` |
| Add MLflow adapter to existing file | `flowcept --init-settings --mlflow -y` |
| Add TensorBoard adapter to existing file | `flowcept --init-settings --tensorboard -y` |
| Switch an existing file to online mode | `flowcept --config-profile full-online -y` |
| Switch an existing file to offline mode | `flowcept --config-profile full-offline -y` |

Adapter flags (`--dask`, `--mlflow`, `--tensorboard`) are **additive** — they append to an existing file without overwriting it.

### 9.4 Verifying the active settings

```bash
flowcept --show-settings        # prints the resolved settings
flowcept --check-services       # checks which services are reachable
```

From Python:
```python
from flowcept import configs
print(configs.DB_FLUSH_MODE)    # "offline" or "online"
print(configs.MQ_ENABLED)
print(configs.MONGO_ENABLED)
```

### 9.5 Start services

```bash
make services-mongo   # Redis + MongoDB via Docker Compose
```

### 9.6 Checklist before instrumenting

1. `FLOWCEPT_SETTINGS_PATH` is set (or user is aware the default `~/.flowcept/settings.yaml` will be used)
2. Settings file exists (`flowcept --init-settings -y` or `--full -y`)
3. If online mode: services are running (`flowcept --check-services`)
4. If using adapters (Dask, MLflow, TensorBoard): adapter section is in the settings file

---

## 10. Interpreting Natural-Language Configuration Requests

Users will describe what they want in plain language. Your job is to map their intent to the right settings keys and CLI commands, then apply them. Follow this process:

1. **Identify the flush mode** — online or offline?
2. **Identify the MQ** — Redis (default), Kafka, or Mofka? Any host/port/URI?
3. **Identify the DB** — MongoDB, LMDB, both, or none?
4. **Identify connection details** — hosts, ports, URIs, paths
5. **Identify adapters** — Dask, MLflow, TensorBoard?
6. **Identify extras** — telemetry, instrumentation, debug, dump buffer?

Then: start from the right base (`--init-settings -y` or `--full -y`), apply a profile if one fits, then patch remaining keys directly in the YAML.

---

### 10.1 Settings reference map

**Flush mode**
```yaml
project:
  db_flush_mode: offline   # or "online"
```

**Message queue (MQ)**
```yaml
mq:
  enabled: true
  type: redis        # or "kafka" or "mofka"
  host: localhost
  port: 6379
  uri: redis://user:pass@host:6379   # alternative to host+port
  channel: interception
  buffer_size: 50
  insertion_buffer_time_secs: 5
  same_as_kvdb: false   # true = reuse kv_db connection params for MQ
```

**Key-value store (Redis, used for coordination)**
```yaml
kv_db:
  enabled: true
  host: localhost
  port: 6379
  uri: redis://...   # alternative
```

**MongoDB**
```yaml
databases:
  mongodb:
    enabled: true
    host: localhost
    port: 27017
    db: flowcept
```

**LMDB (local file-based, no external service)**
```yaml
databases:
  lmdb:
    enabled: true
    path: flowcept_lmdb   # relative or absolute path
```

**Offline dump buffer**
```yaml
project:
  dump_buffer:
    enabled: true
    path: flowcept_buffer.jsonl
```

**Kafka-specific**
```yaml
mq:
  type: kafka
  host: localhost
  port: 9092
  # group_id: auto
```

**Mofka-specific**
```yaml
mq:
  type: mofka
  host: localhost
  port: 9092
  group_file: mofka.json
```

**Telemetry**
```yaml
telemetry_capture:
  cpu: true
  per_cpu: false
  mem: true
  disk: false
  network: false
  gpu: ~       # ~ = None = disabled; or list e.g. [used, temperature]
  machine_info: false
  process_info: false
```

**Instrumentation (torch)**
```yaml
instrumentation:
  enabled: true
  torch:
    what: parent_and_children   # or "parent_only"
    children_mode: lightweight  # or telemetry, tensor_inspection
    capture_epochs_at_every: 1
    register_workflow: true
```

**Logging**
```yaml
log:
  log_file_level: error    # error, debug, info, critical, disable
  log_stream_level: error
```

**Debug**
```yaml
project:
  debug: true
```

---

### 10.2 Built-in profiles (use when they fit)

| Profile | What it sets |
|---------|-------------|
| `full-online` | online mode, Redis MQ + KV, MongoDB enabled, LMDB disabled, buffer flush every 5s |
| `full-offline` | offline mode, dump buffer enabled, all services disabled |
| `mq-only` | online mode, Redis MQ only, no DB |
| `full-telemetry` | enables all telemetry capture fields (can combine with any other profile) |

Apply with: `flowcept --config-profile <name> -y`

---

### 10.3 Examples — request → actions

**"Configure flowcept with full online, using Redis at URI `redis://myhost:6380` and local LMDB"**
```bash
flowcept --init-settings -y
flowcept --config-profile full-online -y
```
Then patch the YAML at `$FLOWCEPT_SETTINGS_PATH`:
```yaml
mq:
  uri: redis://myhost:6380
  same_as_kvdb: true     # reuse same Redis for kv_db
kv_db:
  enabled: true
databases:
  mongodb:
    enabled: false
  lmdb:
    enabled: true
    path: ./flowcept_lmdb
```

---

**"Use Kafka on port 9092 at broker.internal, store to MongoDB at mongo.internal:27017"**
```bash
flowcept --init-settings -y
flowcept --config-profile full-online -y
```
Patch:
```yaml
mq:
  type: kafka
  host: broker.internal
  port: 9092
kv_db:
  enabled: true
  host: localhost     # Redis still needed for kv_db coordination
databases:
  mongodb:
    enabled: true
    host: mongo.internal
    port: 27017
  lmdb:
    enabled: false
```

---

**"Run fully offline, save buffer to /tmp/my_run.jsonl"**
```bash
flowcept --init-settings -y
flowcept --config-profile full-offline -y
```
Patch:
```yaml
project:
  dump_buffer:
    enabled: true
    path: /tmp/my_run.jsonl
```

---

**"Online with Redis at localhost, no persistent DB, with CPU and memory telemetry"**
```bash
flowcept --init-settings -y
flowcept --config-profile mq-only -y
flowcept --config-profile full-telemetry -y
```
Patch:
```yaml
kv_db:
  enabled: true
  host: localhost
  port: 6379
```

---

**"Full online with Dask and MLflow adapters"**
```bash
flowcept --init-settings --full -y
flowcept --init-settings --dask -y
flowcept --init-settings --mlflow -y
```

---

**"Same Redis instance for both MQ and KV store"**
```yaml
mq:
  enabled: true
  host: localhost
  port: 6379
  same_as_kvdb: true   # tells flowcept not to open a second connection
kv_db:
  enabled: true
  host: localhost
  port: 6379
```

---

### 10.4 How to patch the YAML directly

When CLI commands don't cover a specific key (host, port, URI, path), edit the settings file directly. Always use `$FLOWCEPT_SETTINGS_PATH` if set:

```python
import os
from omegaconf import OmegaConf
from pathlib import Path

settings_path = Path(os.getenv("FLOWCEPT_SETTINGS_PATH",
                               Path.home() / ".flowcept" / "settings.yaml"))
cfg = OmegaConf.load(settings_path)
OmegaConf.update(cfg, "mq.uri", "redis://myhost:6380")
OmegaConf.update(cfg, "mq.same_as_kvdb", True)
OmegaConf.update(cfg, "databases.lmdb.enabled", True)
OmegaConf.update(cfg, "databases.mongodb.enabled", False)
OmegaConf.save(cfg, settings_path)
```

Or edit the YAML file directly as a text file if that is simpler.

After any change, verify:
```bash
flowcept --show-settings
flowcept --check-services
```
