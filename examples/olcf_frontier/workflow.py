"""
Multi-node, multi-process Flowcept provenance example using mpi4py.

Rank 0 opens a Flowcept context (which auto-generates the workflow_id),
broadcasts it to all ranks, then all ranks run instrumented tasks with
start_persistence=False — the standalone consumer service handles LMDB writes.

Usage (inside Slurm after Redis and consumer are running):
    srun --ntasks=$SLURM_NTASKS python workflow.py
"""

import json
import os
import time
import numpy as np
from mpi4py import MPI
import torch
from flowcept import Flowcept
from flowcept.configs import INSERTION_BUFFER_TIME
from flowcept.instrumentation.flowcept_task import flowcept_task


HERE = os.path.dirname(os.path.abspath(__file__))

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()


@flowcept_task
def compute(rank: int, step: int, value: float) -> dict:
    return {"result": value * (rank + 1) + step}


@flowcept_task
def summarize(rank: int, partial_results: list) -> dict:
    return {"summary": sum(r["result"] for r in partial_results), "n_steps": len(partial_results)}


@flowcept_task
def cpu_compute(n: int = 2000) -> dict:
    import tempfile
    a = np.random.rand(n, n)
    b = np.random.rand(n, n)
    c = np.dot(a, b)
    _, s, _ = np.linalg.svd(c, full_matrices=False)
    with tempfile.NamedTemporaryFile(delete=True, suffix=".bin", dir=HERE) as f:
        np.save(f, c)
        f.flush()
        os.fsync(f.fileno())
    return {"top_singular_value": float(s[0]), "matrix_size": n}


@flowcept_task
def gpu_matmul(size: int = 1024) -> dict:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    a = torch.randn(size, size, device=device)
    b = torch.randn(size, size, device=device)
    c = torch.matmul(a, b)
    torch.cuda.synchronize()
    return {"frobenius_norm": c.norm().item()}


def save_outputs(workflow_id: str) -> None:
    base_dir = os.path.join(HERE, "flowcept_output")
    reports_dir = os.path.join(base_dir, "reports")
    tasks_dir = os.path.join(base_dir, "tasks")
    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(tasks_dir, exist_ok=True)

    Flowcept.generate_report(
        report_type="workflow_card",
        format="markdown",
        workflow_id=workflow_id,
        output_path=os.path.join(reports_dir, f"workflow_card_{workflow_id}.md"),
    )
    Flowcept.generate_report(
        report_type="provenance_report",
        format="pdf",
        workflow_id=workflow_id,
        output_path=os.path.join(reports_dir, f"provenance_report_{workflow_id}.pdf"),
    )
    Flowcept.db.dump_to_file(
        collection="tasks",
        filter={"workflow_id": workflow_id},
        output_file=os.path.join(tasks_dir, f"tasks_{workflow_id}.parquet"),
        export_format="parquet",
        should_zip=False,
    )
    workflows = Flowcept.db.query(filter={"workflow_id": workflow_id}, collection="workflows")
    with open(os.path.join(tasks_dir, f"workflow_{workflow_id}.json"), "w") as f:
        json.dump(workflows, f, indent=2, default=str)

    print(f"[rank 0] Output written to {base_dir}", flush=True)


def run_rank_work(workflow_id: str) -> None:
    n_steps = 5
    results = []

    with Flowcept(
        workflow_id=workflow_id,
        workflow_name=f"frontier_mpi_rank_{rank}",
        start_persistence=False,
        check_safe_stops=False,
    ):
        for step in range(n_steps):
            out = compute(rank=rank, step=step, value=float(rank * 10 + step))
            results.append(out)
        summarize(rank=rank, partial_results=results)
        cpu_compute(n=2000)
        gpu_matmul(size=1024)


if __name__ == "__main__":
    if rank == 0:
        fc = Flowcept(workflow_name="frontier_mpi_main", start_persistence=False, check_safe_stops=False)
        fc.start()
        workflow_id = fc.current_workflow_id
        print(f"[rank 0] workflow_id={workflow_id}  nranks={size}", flush=True)
    else:
        workflow_id = None

    workflow_id = comm.bcast(workflow_id, root=0)

    t0 = time.perf_counter()
    run_rank_work(workflow_id)
    comm.Barrier()
    elapsed = time.perf_counter() - t0

    if rank == 0:
        fc.stop()
        print(f"[rank 0] Makespan: {elapsed:.3f}s", flush=True)
        print(f"[rank 0] Done. Query LMDB with workflow_id={workflow_id}", flush=True)

        time.sleep(INSERTION_BUFFER_TIME + 2)  # wait for consumer to flush MQ → LMDB before querying
        save_outputs(workflow_id)
