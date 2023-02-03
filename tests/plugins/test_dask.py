import unittest
import threading
from time import sleep

from flowcept.flowcept_consumer.doc_db.document_db_dao import DocumentDBDao
from flowcept.flowcept_consumer.main import (
    main,
)


def dummy_func1(x):
    return x * 2


def dummy_func2(x):
    return x + x


def dummy_func3(x):
    return x + 2


class TestDask(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestDask, self).__init__(*args, **kwargs)
        self.client = TestDask._setup_local_dask_cluster()
        #self.scheduler_interceptor = DaskSchedulerInterceptor()
        #self.scheduler_interceptor = DaskSchedulerInterceptor()

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
        threading.Thread(target=main, daemon=True).start()
        sleep(3)

    def test_pure_workflow(self):
        i1 = 1
        o1 = self.client.submit(dummy_func1, i1)
        o2 = self.client.submit(dummy_func2, o1)
        print(o2.result())
        return o2.key

    def test_observer_and_consumption(self):
        doc_dao = DocumentDBDao()
        self._init_consumption()
        o2_task_id = self.test_pure_workflow()
        sleep(10)
        assert len(doc_dao.find({"task_id": o2_task_id})) > 0


