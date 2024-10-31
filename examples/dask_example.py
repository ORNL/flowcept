# Make sure you run `pip install flowcept[dask]` first.
from dask.distributed import Client, LocalCluster

from flowcept import Flowcept, FlowceptDaskSchedulerAdapter, FlowceptDaskWorkerAdapter
from flowcept.flowceptor.adapters.dask.dask_plugins import register_dask_workflow


def add(x, y):
    return x + y


def multiply(x, y):
    return x * y


def sum_list(values):
    return sum(values)


if __name__ == "__main__":

    # Starting a local Dask cluster
    cluster = LocalCluster(n_workers=1)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)

    # Registering Flowcept's worker and scheduler adapters
    scheduler.add_plugin(FlowceptDaskSchedulerAdapter(scheduler))
    client.register_plugin(FlowceptDaskWorkerAdapter())

    # Registering a Dask workflow in Flowcept's database
    wf_id = register_dask_workflow(client)
    print(f"workflow_id={wf_id}")

    # Start Flowcept's Dask observer
    flowcept = Flowcept("dask").start()
    t1 = client.submit(add, 1, 2)
    t2 = client.submit(multiply, 3, 4)
    t3 = client.submit(add, t1.result(), t2.result())
    t4 = client.submit(sum_list, [t1, t2, t3])
    result = t4.result()
    print("Result:", result)

    # Closing Dask and Flowcept
    client.close()
    cluster.close()
    flowcept.stop()

    # Querying Flowcept's database about this run
    print(f"t1_key={t1.key}")
    print("Getting first task only:")
    task1 = Flowcept.db.query(filter={"task_id": t1.key})[0]
    assert task1["workflow_id"] == wf_id
    print(task1)
    print("Getting all tasks from this workflow:")
    all_tasks = Flowcept.db.query(filter={"workflow_id": wf_id})
    assert len(all_tasks) == 4
    print(all_tasks)
    print("Getting workflow info:")
    wf_info = Flowcept.db.query(filter={"workflow_id": wf_id}, type="workflow")[0]
    assert wf_info["workflow_id"] == wf_id
    print(wf_info)
