import unittest
from time import sleep
import numpy as np

from dask.distributed import Client, LocalCluster

from flowcept import FlowceptConsumerAPI, TaskQueryAPI, DBAPI
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import (
    assert_by_querying_tasks_until,
    evaluate_until,
)
from flowcept.flowceptor.adapters.dask.dask_plugins import set_dask_workflow
from tests.adapters.dask_test_utils import (
    setup_local_dask_cluster,
    close_dask,
)


def dummy_func1(x):
    cool_var = "cool value"  # test if we can intercept this var
    print(cool_var)
    y = cool_var
    return x * 2


def dummy_func2(y):
    return y + y


def dummy_func3(z, w):
    return {"r": z + w}


def dummy_func4(x_obj):
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
        self.db_api = DBAPI()
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        (
            TestDask.client,
            TestDask.cluster,
            TestDask.consumer,
        ) = setup_local_dask_cluster(TestDask.consumer, 2)

    def atest_pure_workflow(self):
        wf_id = set_dask_workflow(self.client)
        i1 = np.random.random()
        o1 = self.client.submit(dummy_func1, i1)
        o2 = TestDask.client.submit(dummy_func2, o1)
        self.logger.debug(o2.result())
        self.logger.debug(o2.key)
        return wf_id, o2.key

    def test_dummyfunc(self):
        set_dask_workflow(self.client)
        i1 = np.random.random()
        o1 = self.client.submit(dummy_func1, i1)
        # self.logger.debug(o1.result())
        return o1.key

    def test_long_workflow(self):
        i1 = np.random.random()
        set_dask_workflow(self.client)
        o1 = TestDask.client.submit(dummy_func1, i1)
        o2 = TestDask.client.submit(dummy_func2, o1)
        o3 = TestDask.client.submit(dummy_func3, o1, o2)
        self.logger.debug(o3.result())
        return o3.key

    def varying_args(self):
        i1 = np.random.random()
        o1 = TestDask.client.submit(dummy_func3, i1, w=2)
        result = o1.result()
        assert result["r"] > 0
        self.logger.debug(result)
        self.logger.debug(o1.key)
        return o1.key

    def test_map_workflow(self):
        i1 = np.random.random(3)
        set_dask_workflow(self.client)
        o1 = TestDask.client.map(dummy_func1, i1)
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
        set_dask_workflow(self.client)
        o1 = TestDask.client.map(dummy_func4, i1)
        for o in o1:
            result = o.result()
            assert result["z"] > 0
            self.logger.debug(o.key, result)
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
        wf_id, o2_task_id = self.atest_pure_workflow()
        print("Task_id=" + o2_task_id)
        print("wf_id=" + wf_id)
        print("Done workflow!")
        assert assert_by_querying_tasks_until(
            {"task_id": o2_task_id},
            condition_to_evaluate=lambda docs: "telemetry_at_end" in docs[0],
        )
        assert evaluate_until(
            lambda: self.db_api.get_workflow(workflow_id=wf_id) is not None,
            msg="Checking if workflow object was saved in db",
        )
        print("All conditions met!")

    def test_observer_and_consumption_varying_args(self):
        o2_task_id = self.varying_args()
        sleep(3)
        assert assert_by_querying_tasks_until({"task_id": o2_task_id})

    def test_observer_and_consumption_error_task(self):
        o2_task_id = self.error_task_submission()
        assert assert_by_querying_tasks_until(
            {"task_id": o2_task_id},
            condition_to_evaluate=lambda docs: "exception"
            in docs[0]["stderr"],
        )

    @classmethod
    def tearDownClass(cls):
        print("Ending tests!")
        try:
            close_dask(TestDask.client, TestDask.cluster)
        except Exception as e:
            print(e)
            pass
        if TestDask.consumer:
            TestDask.consumer.stop()
