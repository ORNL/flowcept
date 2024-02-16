import unittest
from time import sleep
from uuid import uuid4
import numpy as np

from dask.distributed import Client

from flowcept import FlowceptConsumerAPI, TaskQueryAPI, DBAPI
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import assert_by_querying_task_collections_until


def dummy_func1(x, workflow_id=None):
    cool_var = "cool value"  # test if we can intercept this var
    print(cool_var)
    y = cool_var
    return x * 2


class TestDaskContextMgmt(unittest.TestCase):
    client: Client = None

    def __init__(self, *args, **kwargs):
        super(TestDaskContextMgmt, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        TestDaskContextMgmt.client = (
            TestDaskContextMgmt._setup_local_dask_cluster()
        )

    @staticmethod
    def _setup_local_dask_cluster(n_workers=2):
        from dask.distributed import Client, LocalCluster
        from flowcept import (
            FlowceptDaskSchedulerAdapter,
            FlowceptDaskWorkerAdapter,
        )

        cluster = LocalCluster(n_workers=n_workers)
        scheduler = cluster.scheduler
        client = Client(scheduler.address)

        # Instantiate and Register FlowceptPlugins, which are the ONLY
        # additional steps users would need to do in their code:
        scheduler.add_plugin(FlowceptDaskSchedulerAdapter(scheduler))

        client.register_worker_plugin(FlowceptDaskWorkerAdapter())

        return client

    def test_workflow(self):
        i1 = np.random.random()
        wf_id = f"wf_{uuid4()}"
        with FlowceptConsumerAPI():
            o1 = self.client.submit(dummy_func1, i1, workflow_id=wf_id)
            self.logger.debug(o1.result())
            self.logger.debug(o1.key)
            sleep(5)
            TestDaskContextMgmt.client.shutdown()

        assert assert_by_querying_task_collections_until(
            DocumentDBDao(),
            {"task_id": o1.key},
            condition_to_evaluate=lambda docs: "ended_at" in docs[0],
        )
