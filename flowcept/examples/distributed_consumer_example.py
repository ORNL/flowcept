import os
import subprocess
import uuid
from time import sleep
from flowcept import Flowcept, FlowceptTask

def execute_cmd(command: str) -> int:
    """
    Executes a command using nohup in the background and returns the process ID (PID).

    Parameters
    ----------
    command : str
        The command to be executed.

    Returns
    -------
    int
        The PID of the background process.
    """
    try:
        # Append nohup and redirect outputs to /dev/null for background execution
        nohup_command = f"nohup {command} > /dev/null 2>&1 & echo $!"
        # Execute the command in a shell and capture the PID
        print(f"Executing: {nohup_command}")
        process = subprocess.run(nohup_command, shell=True, check=True, executable='/bin/bash', text=True, capture_output=True)
        pid = int(process.stdout.strip())  # Get the PID from the output
        print(f"Started process with PID: {pid}")
        return pid
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {command}\n{e}")
        return -1


def kill_process(pid: int) -> None:
    """
    Kills a process by its PID.

    Parameters
    ----------
    pid : int
        The PID of the process to be killed.
    """
    try:
        os.kill(pid, 9)  # Send SIGKILL to the process
        print(f"Process {pid} killed successfully.")
    except ProcessLookupError:
        print(f"No process found with PID: {pid}.")
    except PermissionError:
        print(f"Permission denied to kill PID: {pid}.")


def simple_flowcept_task(workflow_id):

    with Flowcept(start_persistence=False, workflow_id=workflow_id, bundle_exec_id=workflow_id):
        with FlowceptTask(used={"a": 1}) as t:
            t.end(generated={"b": 2})


if __name__ == "__main__":

    workflow_id = str(uuid.uuid4())
    print(workflow_id)

    pid = execute_cmd(f"python -c 'from flowcept import Flowcept; Flowcept.start_consumption_services(\"{workflow_id}\")'")
    sleep(1)

    simple_flowcept_task(workflow_id)

    sleep(15)  # Give enough time for the consumer services to do their thing

    kill_process(pid)

    tasks = Flowcept.db.query({"workflow_id": workflow_id})
    assert len(tasks) == 1
    print(tasks)
