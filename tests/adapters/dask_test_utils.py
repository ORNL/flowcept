from dask.distributed import Client, LocalCluster
from distributed import Status

from flowcept import FlowceptConsumerAPI


def close_dask(client, cluster):
    """
    We must close dask so that the Dask plugins at the workers and scheduler will send the stop signal, which is required for flowcept to stop gracefully (otherwise it will run forever waiting for this stop signal.
    The trick part was to find the correct order of closures for dask, that's why I created this [very simple] method, which might be reused in other tests.
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


def setup_local_dask_cluster(consumer=None, n_workers=1):
    from flowcept import (
        FlowceptDaskSchedulerAdapter,
        FlowceptDaskWorkerAdapter,
    )

    if consumer is None or not consumer.is_started:
        consumer = FlowceptConsumerAPI().start()

    cluster = LocalCluster(n_workers=n_workers)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)

    scheduler.add_plugin(FlowceptDaskSchedulerAdapter(scheduler))
    client.register_worker_plugin(FlowceptDaskWorkerAdapter())

    return client, cluster, consumer
