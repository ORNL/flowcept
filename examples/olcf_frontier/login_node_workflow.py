"""
Login-node smoke test — single rank, no MPI.

Mimics workflow.py as closely as possible to validate the full pipeline
(Redis → Flowcept consumer → LMDB → reports/parquet) before submitting to Slurm.
Infrastructure (Redis + consumer) is managed by run_login_node_workflow.sh.
"""

import json
import os
import time

from flowcept import Flowcept
from flowcept.configs import INSERTION_BUFFER_TIME
from flowcept.instrumentation.flowcept_task import flowcept_task

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Task definitions (identical to workflow.py) ───────────────────────────────

@flowcept_task(output_names=["result"])
def compute(rank: int, step: int, value: float) -> dict:
    return {"result": value * (rank + 1) + step}


@flowcept_task(output_names=["summary"])
def summarize(rank: int, partial_results: list) -> dict:
    return {"summary": sum(r["result"] for r in partial_results), "n_steps": len(partial_results)}


# ── Output saving (identical to workflow.py) ──────────────────────────────────

def save_outputs(workflow_id: str) -> None:
    base_dir = os.path.join(HERE, "flowcept_output")
    reports_dir = os.path.join(base_dir, "reports")
    tasks_dir = os.path.join(base_dir, "tasks")
    os.makedirs(reports_dir, exist_ok=True)
    os.makedirs(tasks_dir, exist_ok=True)

    Flowcept.generate_report(
        report_type="provenance_card",
        format="markdown",
        workflow_id=workflow_id,
        output_path=os.path.join(reports_dir, f"provenance_card_{workflow_id}.md"),
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

    print(f"Output written to {base_dir}", flush=True)


# ── Single-rank workflow (mirrors workflow.py rank-0 path) ────────────────────

def run_rank_work(workflow_id: str, rank: int = 0, n_steps: int = 5) -> None:
    with Flowcept(
        workflow_id=workflow_id,
        workflow_name=f"frontier_mpi_rank_{rank}",
        start_persistence=False,
        check_safe_stops=False,
    ):
        results = [compute(rank=rank, step=s, value=float(rank * 10 + s)) for s in range(n_steps)]
        summarize(rank=rank, partial_results=results)


if __name__ == "__main__":
    fc = Flowcept(workflow_name="frontier_mpi_main", start_persistence=False, check_safe_stops=False)
    fc.start()
    workflow_id = fc.current_workflow_id
    print(f"workflow_id={workflow_id}", flush=True)

    t0 = time.perf_counter()
    run_rank_work(workflow_id)
    elapsed = time.perf_counter() - t0

    fc.stop()
    print(f"Makespan: {elapsed:.3f}s", flush=True)

    time.sleep(INSERTION_BUFFER_TIME + 2)  # wait for consumer to flush MQ → LMDB before querying
    save_outputs(workflow_id)
