import unittest
from time import sleep
from flowcept import (
    Flowcept,
    flowcept_task,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import assert_by_querying_tasks_until, get_current_config_values
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor

from src.flowcept.configs import INSERTION_BUFFER_TIME, MONGO_ENABLED, MQ_INSERTION_BUFFER_TIME


@flowcept_task
def sum_one(n):
    return n + 1


@flowcept_task
def mult_two(n):
    return n * 2


@flowcept_task
def sum_one_(x):
    return {"y": x + 1}


@flowcept_task
def mult_two_(y):
    return {"z": y * 2}


class FlowceptAPITest(unittest.TestCase):

    def test_is_alive(self):
        assert Flowcept.services_alive()


    def test_configs(self):
        current_configs = get_current_config_values()
        assert "LOG_FILE_PATH" in current_configs

    def test_simple_workflow(self):
        assert Flowcept.services_alive()

        with Flowcept(workflow_name="test_workflow"):
            n = 3
            o1 = sum_one(n)
            o2 = mult_two(o1)
            print(o2)

        assert assert_by_querying_tasks_until(
            {"workflow_id": Flowcept.current_workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == 2,
        )

        print("workflow_id", Flowcept.current_workflow_id)

        print(Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id}))

        assert len(Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})) == 2
        assert (
            len(
                Flowcept.db.query(
                    collection="workflows",
                    filter={"workflow_id": Flowcept.current_workflow_id},
                )
            )
            == 1
        )

    def test_instrumentation_interceptor_singleton(self):
        logger = FlowceptLogger()
        try:
            InstrumentationInterceptor()
        except Exception as e:
            logger.debug(f"This exception is expected: {e}")

        a = InstrumentationInterceptor.get_instance()
        b = InstrumentationInterceptor.get_instance()

        assert a == b
        assert id(a) == id(b)

    @unittest.skip("Test only for dev.")
    def test_continuous_run(self):
        import numpy as np
        from time import sleep

        with Flowcept(workflow_name="continuous_workflow_test"):
            print(Flowcept.current_workflow_id)
            while True:
                n = np.random.rand()
                o1 = sum_one_(x=n)
                o2 = mult_two_(**o1)
                sleep(10)

    def test_simple_all_consumers(self):
        with Flowcept(workflow_name="test_workflow"):
            n = 3
            o1 = sum_one(n)
            o2 = mult_two(o1)
            print(o2)

    def test_simple_workflow_no_consumers(self):
        with Flowcept(workflow_name="test_workflow3", start_persistence=False):
            n = 3
            o1 = sum_one(n)
            o2 = mult_two(o1)
            print(o2)

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_runtime_query(self):
        N = 5
        with Flowcept(workflow_name="test_workflow"):
            for i in range(N):
                sum_one(i)
                sleep(2.2*(INSERTION_BUFFER_TIME+MQ_INSERTION_BUFFER_TIME))
                tasks = Flowcept.db.get_tasks_from_current_workflow()
                assert len(tasks) == (i+1)
        assert len(Flowcept.db.get_tasks_from_current_workflow()) == N

