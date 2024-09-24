import unittest
import numpy as np

from dask.distributed import Client
from distributed import LocalCluster

from flowcept import Flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.flowceptor.adapters.dask.dask_plugins import (
    register_dask_workflow,
    FlowceptDaskSchedulerAdapter,
    FlowceptDaskWorkerAdapter,
)
from tests.adapters.dask_test_utils import (
    setup_local_dask_cluster,
    close_dask,
)


def dummy_func1(x):
    cool_var = "cool value"  # test if we can intercept this var
    print(cool_var)
    y = cool_var
    return x * 2


class TestDaskContextMgmt(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestDaskContextMgmt, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    def test_workflow(self):
        cluster = LocalCluster(n_workers=2)
        scheduler = cluster.scheduler
        client = Client(scheduler.address)
        scheduler.add_plugin(FlowceptDaskSchedulerAdapter(scheduler))
        client.register_plugin(FlowceptDaskWorkerAdapter())
        register_dask_workflow(client)

        with Flowcept("dask"):
            i1 = np.random.random()
            o1 = client.submit(dummy_func1, i1)
            self.logger.debug(o1.result())
            self.logger.debug(o1.key)

            close_dask(client, cluster)
            # stop signal sent to doc inserter must be sent after
            # all other interceptors stopped

        assert assert_by_querying_tasks_until(
            {"task_id": o1.key},
            condition_to_evaluate=lambda docs: "ended_at" in docs[0],
        )
