# Flowcept on OLCF Frontier

Multi-node MPI workflow provenance using Redis + LMDB (no MongoDB).

## Prerequisites

**Redis** — compile from source (tested: Redis 8.6.3), but feel free to use container images or pre-built binaries:
```bash
wget https://download.redis.io/redis-stable.tar.gz && tar -xzf redis-stable.tar.gz
cd redis-stable && module load PrgEnv-gnu && make -j8
```

**Python deps** — any env manager works; `run.slurm` uses conda:
```bash
pip install -r requirements.txt
# mpi4py must be built against Cray MPICH:
module load PrgEnv-gnu cray-mpich && pip install --no-binary=mpi4py mpi4py
```

## Settings

`flowcept_settings.yaml` is gitignored. Create from the template and fill in the two paths:
```bash
cp flowcept_settings.example.yaml flowcept_settings.yaml
```

| Key | What to set |
|---|---|
| `mq.bin` | Path to your compiled `redis-server` |
| `mq.conf_file` | Path to `deployment/redis_conf/redis.conf` in your Flowcept clone |

## Login-node smoke test (no Slurm needed)

Verify the full pipeline before submitting:
```bash
bash run_login_node_workflow.sh
```

## Run on Slurm

```bash
export CONDA_ROOT=/path/to/your/miniconda
bash submit.sh <project-account>
```

## AMD GPU Telemetry (optional)

Frontier has AMD MI250X GPUs. To capture GPU metrics (utilization, memory, power, temperature):

**Install:**
```bash
pip install flowcept[amd]
```

**Set `LD_LIBRARY_PATH`** to the ROCm version matching your installed `amdsmi`.
As of 2026-05-21, the working combination on Frontier is `amdsmi==7.0.2` + ROCm 7.0.2:
```bash
export LD_LIBRARY_PATH=/opt/rocm-7.0.2/lib:$LD_LIBRARY_PATH
```

To find the newest available ROCm on Frontier and pick the right `amdsmi` version:
```bash
ls /opt/rocm-*              # list installed ROCm versions (e.g. /opt/rocm-7.0.2)
pip index versions amdsmi   # list all amdsmi versions on PyPI
# pick the amdsmi X.Y.Z that matches your /opt/rocm-X.Y.Z, then:
pip install amdsmi==X.Y.Z
```

**Verify:**
```bash
python -c "from amdsmi import amdsmi_init, amdsmi_get_processor_handles; amdsmi_init(); print(len(amdsmi_get_processor_handles()), 'GPU(s) found')"
```

**Enable in `flowcept_settings.yaml`:**
```yaml
telemetry_capture:
  gpu:
    - used
    - activity
    - power
    - temperature
```

Add `export LD_LIBRARY_PATH=/opt/rocm-7.0.2/lib:$LD_LIBRARY_PATH` to `run.slurm` and `run_login_node_workflow.sh` before starting Redis.

---

## Tuning overhead

**Buffer size / flush interval** — two independent buffers (producer → Redis, consumer → LMDB). Increase both for many short-lived tasks on many ranks:

```yaml
mq:
  buffer_size: 500              # records per Redis publish (default: 1)
  insertion_buffer_time_secs: 5 # force-flush interval in seconds (default: 1)

db_buffer:
  buffer_size: 500              # records per LMDB write transaction (default: 50)
  insertion_buffer_time_secs: 5
```

**Telemetry** — disable unused subsystems to reduce per-task overhead. On Frontier, `disk` misses Lustre; use `process_info` instead:

```yaml
telemetry_capture:
  cpu: true
  mem: true
  disk: false        # block-level; does NOT capture Lustre IO
  network: false
  process_info: true # /proc/<pid>/io — captures Lustre IO correctly
  gpu:               # AMD only; requires flowcept[amd] + LD_LIBRARY_PATH
    - used
    - temperature
```

---

## Output

Each run writes to `flowcept_output/`:
- `lmdb/<job_id>/` — raw LMDB database
- `tasks/` — parquet + workflow JSON
- `reports/` — provenance card (MD) and report (PDF)
