import unittest


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

    def test_simple_workflow(self):
        i1 = 1
        o1 = self.client.submit(dummy_func1, i1)
        o2 = self.client.submit(dummy_func2, o1)
        print(o2.result())
