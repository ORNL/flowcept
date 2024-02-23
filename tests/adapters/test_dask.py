import unittest
from time import sleep
from uuid import uuid4
import numpy as np

from dask.distributed import Client, LocalCluster
from distributed import Status

from flowcept import FlowceptConsumerAPI, TaskQueryAPI
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import assert_by_querying_task_collections_until


def dummy_func1(x, workflow_id=None):
    cool_var = "cool value"  # test if we can intercept this var
    print(cool_var)
    y = cool_var
    return x * 2


def dummy_func2(y, workflow_id=None):
    return y + y


def dummy_func3(z, w, workflow_id=None):
    return {"r": z + w}


def dummy_func4(x_obj, workflow_id=None):
    return {"z": x_obj["x"] * 2}


def forced_error_func(x):
    raise Exception(f"This is a forced error: {x}")


class TestDask(unittest.TestCase):
    client: Client = None
    cluster: LocalCluster = None
    consumer: FlowceptConsumerAPI = None

    def __init__(self, *args, **kwargs):
        super(TestDask, self).__init__(*args, **kwargs)
        self.query_api = TaskQueryAPI()
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        (
            TestDask.client,
            TestDask.cluster,
        ) = TestDask.setup_local_dask_cluster(2)

    @staticmethod
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

    @staticmethod
    def setup_local_dask_cluster(n_workers=1):
        from flowcept import (
            FlowceptDaskSchedulerAdapter,
            FlowceptDaskWorkerAdapter,
        )

        if TestDask.consumer is None or not TestDask.consumer.is_started:
            TestDask.consumer = FlowceptConsumerAPI().start()

        cluster = LocalCluster(n_workers=n_workers)
        scheduler = cluster.scheduler
        client = Client(scheduler.address)

        scheduler.add_plugin(FlowceptDaskSchedulerAdapter(scheduler))
        client.register_worker_plugin(FlowceptDaskWorkerAdapter())

        return client, cluster

    def atest_pure_workflow(self):
        i1 = np.random.random()
        wf_id = f"wf_{uuid4()}"
        o1 = self.client.submit(dummy_func1, i1, workflow_id=wf_id)
        o2 = TestDask.client.submit(dummy_func2, o1, workflow_id=wf_id)
        self.logger.debug(o2.result())
        self.logger.debug(o2.key)
        sleep(3)
        return o2.key

    def test_dummyfunc(self):
        i1 = np.random.random()
        wf_id = f"wf_{uuid4()}"
        o1 = self.client.submit(dummy_func1, i1, workflow_id=wf_id)
        # self.logger.debug(o1.result())
        sleep(3)
        return o1.key

    def test_long_workflow(self):
        i1 = np.random.random()
        wf_id = f"wf_{uuid4()}"
        o1 = TestDask.client.submit(dummy_func1, i1, workflow_id=wf_id)
        o2 = TestDask.client.submit(dummy_func2, o1, workflow_id=wf_id)
        o3 = TestDask.client.submit(dummy_func3, o1, o2, workflow_id=wf_id)
        self.logger.debug(o3.result())
        sleep(3)
        return o3.key

    def varying_args(self):
        i1 = np.random.random()
        o1 = TestDask.client.submit(dummy_func3, i1, w=2)
        result = o1.result()
        assert result["r"] > 0
        self.logger.debug(result)
        self.logger.debug(o1.key)
        sleep(3)
        return o1.key

    def test_map_workflow(self):
        i1 = np.random.random(3)
        wf_id = f"wf_{uuid4()}"
        o1 = TestDask.client.map(dummy_func1, i1, workflow_id=wf_id)
        for o in o1:
            result = o.result()
            assert result > 0
            self.logger.debug(f"{o.key}, {result}")
        sleep(3)
        return o1

    def test_map_workflow_kwargs(self):
        i1 = [
            {"x": np.random.random(), "y": np.random.random()},
            {"x": np.random.random()},
            {"x": 4, "batch_norm": False},
            {"x": 6, "batch_norm": True, "empty_string": ""},
        ]
        wf_id = f"wf_{uuid4()}"
        o1 = TestDask.client.map(dummy_func4, i1, workflow_id=wf_id)
        for o in o1:
            result = o.result()
            assert result["z"] > 0
            self.logger.debug(o.key, result)
        sleep(3)
        return o1

    def error_task_submission(self):
        i1 = np.random.random()
        o1 = TestDask.client.submit(forced_error_func, i1)
        try:
            self.logger.debug(o1.result())
        except:
            pass
        return o1.key

    def test_observer_and_consumption(self):
        o2_task_id = self.atest_pure_workflow()
        print("Task_id=" + o2_task_id)
        print("Done workflow!")
        assert assert_by_querying_task_collections_until(
            self.query_api,
            {"task_id": o2_task_id},
            condition_to_evaluate=lambda docs: "telemetry_at_end" in docs[0],
        )
        print("Query condition met!")

    def test_observer_and_consumption_varying_args(self):
        o2_task_id = self.varying_args()
        sleep(3)
        assert assert_by_querying_task_collections_until(
            self.query_api, {"task_id": o2_task_id}
        )

    def test_observer_and_consumption_error_task(self):
        o2_task_id = self.error_task_submission()
        assert assert_by_querying_task_collections_until(
            self.query_api,
            {"task_id": o2_task_id},
            condition_to_evaluate=lambda docs: "exception"
            in docs[0]["stderr"],
        )

    @classmethod
    def tearDownClass(cls):
        print("Ending tests!")
        try:
            TestDask.close_dask(TestDask.client, TestDask.cluster)
        except Exception as e:
            print(e)
            pass

        if TestDask.consumer:
            TestDask.consumer.stop()
