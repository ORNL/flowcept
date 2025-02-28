from distributed import Client, LocalCluster
from distributed import Status

from flowcept import Flowcept


def stop_local_dask_cluster(client, cluster, flowcept=None):
    """
    We must close dask so that the Dask plugins at the workers and scheduler will send the stop signal, which is required for flowcept to stop gracefully (otherwise it will run forever waiting for this stop signal).
    The tricky part was to find the correct order of closures for dask, that's why I created this [very simple] method, which might be reused in other tests.
    From all alternatives, after several trial and errors, what worked best without exceptions being thrown is here in this method. client.shutdown causes the workers to die unexpectedly.

    :param client:
    :param cluster:
    :return:
    """
    print("Going to close Dask, hopefully gracefully!")
    client.close()
    cluster.close()

    assert cluster.status == Status.closed
    assert client.status == "closed"
    print("Dask closed.")
    if flowcept:
        print("Now closing flowcept consumer.")
        flowcept.stop()
        print("Flowcept consumer closed.")


def start_local_dask_cluster(n_workers=1, start_persistence=False):
    cluster = LocalCluster(n_workers=n_workers)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)
    exec_bundle = scheduler.address
    if start_persistence:
        from flowcept import FlowceptDaskWorkerAdapter

        client.register_plugin(FlowceptDaskWorkerAdapter())

        flowcept = Flowcept(interceptors="dask", bundle_exec_id=exec_bundle, dask_client=client).start()

        return client, cluster, flowcept
    else:
        return client, cluster

