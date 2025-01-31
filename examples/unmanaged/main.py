import uuid
import subprocess
import os
from flowcept.flowcept_api.flowcept_controller import Flowcept
from pathlib import Path

def start_workflow():
    """Initialize and start the Flowcept workflow."""
    workflow_id = str(uuid.uuid4())
    flowcept_instance = Flowcept(
        workflow_id=workflow_id,
        workflow_name="Test-Workflow",
        bundle_exec_id=workflow_id
    )
    flowcept_instance.start()
    return workflow_id, flowcept_instance


def run_task(workflow_id, script="simple_task.py"):
    """Run an external Python script with the given workflow ID."""
    process = subprocess.Popen(
        ["python", script, workflow_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    for line in iter(process.stdout.readline, ""):
        print(line, end="")

    process.stdout.close()
    process.wait()


def main():
    """Main function to manage workflow execution."""

    parent_dir = Path(__file__).resolve().parent
    script = os.path.join(parent_dir, "simple_task.py")

    workflow_id, f = start_workflow()

    try:
        run_task(workflow_id, script=script)
    finally:
        f.stop()

    return workflow_id


if __name__ == "__main__":
    workflow_id = main()
    tasks = Flowcept.db.query({"workflow_id": workflow_id})
    assert len(tasks) == 1
    print(f"There is one task for the workflow {workflow_id}.")
