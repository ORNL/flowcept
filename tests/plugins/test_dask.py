import unittest
import threading
from time import sleep
from uuid import uuid4
import numpy as np

from flowcept.commons.doc_db.document_db_dao import DocumentDBDao
from flowcept.commons.doc_db.document_inserter import (
    DocumentInserter,
)


def dummy_func1(x, workflow_id=None):
    return x * 2


def dummy_func2(y, workflow_id=None):
    return y + y


def dummy_func3(z, w, workflow_id=None):
    return {"r": z + w}


def forced_error_func(x):
    raise Exception(f"This is a forced error: {x}")


class TestDask(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TestDask.client = TestDask._setup_local_dask_cluster()
        TestDask.consumer_thread = None

    @staticmethod
    def _setup_local_dask_cluster():
        from dask.distributed import Client, LocalCluster
        from flowcept.flowceptor.plugins.dask.dask_plugins import (
            FlowceptDaskSchedulerPlugin,
            FlowceptDaskWorkerPlugin,
        )

        cluster = LocalCluster(n_workers=2)
        scheduler = cluster.scheduler
        client = Client(scheduler.address)

        # Instantiate and Register FlowceptPlugins, which are the ONLY
        # additional steps users would need to do in their code:
        scheduler_plugin = FlowceptDaskSchedulerPlugin(scheduler)
        scheduler.add_plugin(scheduler_plugin)

        worker_plugin = FlowceptDaskWorkerPlugin()
        client.register_worker_plugin(worker_plugin)

        return client

    def _init_consumption(self):
        TestDask.consumer_thread = threading.Thread(
            target=DocumentInserter().main, daemon=True
        ).start()
        sleep(3)

    def test_pure_workflow(self):
        import numpy as np

        i1 = np.random.random()
        wf_id = f"wf_{uuid4()}"
        o1 = self.client.submit(dummy_func1, i1, workflow_id=wf_id)
        o2 = TestDask.client.submit(dummy_func2, o1, workflow_id=wf_id)
        print(o2.result())
        print(o2.key)
        return o2.key

    def test_long_workflow(self):
        import numpy as np

        i1 = np.random.random()
        wf_id = f"wf_{uuid4()}"
        o1 = TestDask.client.submit(dummy_func1, i1, workflow_id=wf_id)
        o2 = TestDask.client.submit(dummy_func2, o1, workflow_id=wf_id)
        o3 = TestDask.client.submit(dummy_func3, o1, o2, workflow_id=wf_id)
        print(o3.result())
        return o3.key

    def varying_args(self):
        i1 = np.random.random()
        o1 = TestDask.client.submit(dummy_func3, i1, w=2)
        print(o1.result())
        print(o1.key)
        return o1.key

    def error_task_submission(self):
        i1 = np.random.random()
        o1 = TestDask.client.submit(forced_error_func, i1)
        try:
            print(o1.result())
        except:
            pass
        print(o1.key)
        return o1.key

    def test_observer_and_consumption(self):
        doc_dao = DocumentDBDao()
        if TestDask.consumer_thread is None:
            self._init_consumption()
        o2_task_id = self.test_pure_workflow()
        sleep(10)
        assert len(doc_dao.find({"task_id": o2_task_id})) > 0

    def test_observer_and_consumption_varying_args(self):
        doc_dao = DocumentDBDao()
        if TestDask.consumer_thread is None:
            self._init_consumption()
        o2_task_id = self.varying_args()
        sleep(10)
        assert len(doc_dao.find({"task_id": o2_task_id})) > 0

    def test_observer_and_consumption_error_task(self):
        doc_dao = DocumentDBDao()
        if TestDask.consumer_thread is None:
            self._init_consumption()
        o2_task_id = self.error_task_submission()
        sleep(10)
        docs = doc_dao.find({"task_id": o2_task_id})
        assert len(docs) > 0
        assert docs[0]["stderr"]["exception"]
