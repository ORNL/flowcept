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

## Output

Each run writes to `flowcept_output/`:
- `lmdb/<job_id>/` — raw LMDB database
- `tasks/` — parquet + workflow JSON
- `reports/` — provenance card (MD) and report (PDF)
