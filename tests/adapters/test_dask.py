import unittest
import uuid
from time import sleep
import numpy as np

from flowcept import Flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import (
    assert_by_querying_tasks_until,
    evaluate_until,
)
from tests.adapters.dask_test_utils import (
    start_local_dask_cluster,
    stop_local_dask_cluster,
)


def problem_evaluate(phenome, uuid):
    print(phenome, uuid)
    return 1.0


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

    def __init__(self, *args, **kwargs):
        super(TestDask, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    def test_dummyfunc(self):
        client, cluster = start_local_dask_cluster(n_workers=1)
        i1 = np.random.random()
        o1 = client.submit(dummy_func1, i1)
        stop_local_dask_cluster(client, cluster)
        # self.logger.debug(o1.result())

    def test_long_workflow(self):
        client, cluster = start_local_dask_cluster(n_workers=1)
        i1 = np.random.random()
        o1 = client.submit(dummy_func1, i1)
        o2 = client.submit(dummy_func2, o1)
        o3 = client.submit(dummy_func3, o1, o2)
        self.logger.debug(o3.result())
        stop_local_dask_cluster(client, cluster)

    def test_map_workflow(self):
        client, cluster = start_local_dask_cluster(n_workers=1)
        i1 = np.random.random(3)
        o1 = client.map(dummy_func1, i1)
        for o in o1:
            result = o.result()
            assert result > 0
            self.logger.debug(f"{o.key}, {result}")
        stop_local_dask_cluster(client, cluster)

    def test_map_workflow_kwargs(self):
        client, cluster = start_local_dask_cluster(n_workers=1)
        i1 = [
            {"x": np.random.random(), "y": np.random.random()},
            {"x": np.random.random()},
            {"x": 4, "batch_norm": False},
            {"x": 6, "batch_norm": True, "empty_string": ""},
        ]
        o1 = client.map(dummy_func4, i1)
        for o in o1:
            result = o.result()
            assert result["z"] > 0
            self.logger.debug(o.key, result)
        stop_local_dask_cluster(client, cluster)

    def test_a_observer_and_consumption(self):
        client, cluster, flowcept = start_local_dask_cluster(n_workers=1, start_persistence=True)
        i1 = np.random.random()
        o1 = client.submit(dummy_func1, i1)
        o2 = client.submit(dummy_func2, o1)
        self.logger.debug(o2.result())
        self.logger.debug(o2.key)
        print("Task_id=" + o2.key)
        wf_id = Flowcept.current_workflow_id
        print("wf_id=" + wf_id)
        print("Done workflow!")
        sleep(1)
        stop_local_dask_cluster(client, cluster, flowcept)
        assert assert_by_querying_tasks_until(
            {"workflow_id": wf_id, "task_id": o2.key},
            condition_to_evaluate=lambda docs: "ended_at" in docs[0]
            and "y" in docs[0]["used"]
            and len(docs[0]["generated"]) > 0,
        )
        assert evaluate_until(
            lambda: Flowcept.db.get_workflow_object(workflow_id=wf_id) is not None,
            msg="Checking if workflow object was saved in db",
        )
        print("All conditions met!")
        #Flowcept.db.close()

    def test_b_evaluate_submit(self):
        client, cluster, flowcept = start_local_dask_cluster(n_workers=1, start_persistence=True)
        wf_id = Flowcept.current_workflow_id
        print(wf_id)
        phenome = {
            "optimizer": "Adam",
            "lr": 0.0001,
            "betas": [0.8, 0.999],
            "eps": 1e-08,
            "weight_decay": 0.05,
            "ams_grad": 0.5,
            "batch_normalization": True,
            "dropout": True,
            "upsampling": "bilinear",
            "dilation": True,
            "num_filters": 1,
        }

        o1 = client.submit(problem_evaluate, phenome, str(uuid.uuid4()))
        print(o1.result())
        stop_local_dask_cluster(client, cluster, flowcept)
        assert assert_by_querying_tasks_until(
            {"workflow_id": wf_id},
            condition_to_evaluate=lambda docs: "phenome" in docs[0]["used"]
            and len(docs[0]["generated"]) > 0,
            max_trials=30
        )
        assert evaluate_until(
            lambda: Flowcept.db.get_workflow_object(workflow_id=wf_id) is not None,
            msg="Checking if workflow object was saved in db",
        )

    def test_observer_and_consumption_varying_args(self):
        client, cluster, flowcept = start_local_dask_cluster(n_workers=1, start_persistence=True)
        i1 = np.random.random()
        o1 = client.submit(dummy_func3, i1, w=2)
        result = o1.result()
        assert result["r"] > 0
        self.logger.debug(result)
        self.logger.debug(o1.key)
        stop_local_dask_cluster(client, cluster, flowcept)
        assert assert_by_querying_tasks_until({"task_id": o1.key})

    def test_observer_and_consumption_error_task(self):
        client, cluster, flowcept = start_local_dask_cluster(n_workers=1, start_persistence=True)
        i1 = np.random.random()
        o1 = client.submit(forced_error_func, i1)
        try:
            self.logger.debug(o1.result())
        except:
            pass
        stop_local_dask_cluster(client, cluster, flowcept)
        assert assert_by_querying_tasks_until(
            {"task_id": o1.key},
            condition_to_evaluate=lambda docs: "exception" in docs[0]["stderr"],
        )

    @classmethod
    def tearDownClass(cls):
        Flowcept.db.close()
