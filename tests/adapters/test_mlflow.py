import unittest
from time import sleep
import numpy as np
import os
import uuid
import mlflow

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept import MLFlowInterceptor
from flowcept import Flowcept
from flowcept.commons.utils import (
    assert_by_querying_tasks_until,
    evaluate_until,
)


class TestMLFlow(unittest.TestCase):
    interceptor = None

    def __init__(self, *args, **kwargs):
        super(TestMLFlow, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        TestMLFlow.interceptor = MLFlowInterceptor()
        if os.path.exists(TestMLFlow.interceptor.settings.file_path):
            os.remove(TestMLFlow.interceptor.settings.file_path)
        with open(TestMLFlow.interceptor.settings.file_path, "w") as f:
            f.write("")
        sleep(1)
        mlflow.set_tracking_uri(f"sqlite:///{TestMLFlow.interceptor.settings.file_path}")
        mlflow.delete_experiment(mlflow.create_experiment("starter"))
        sleep(1)

    def test_simple_mlflow_run(self):
        self.simple_mlflow_run()

    def simple_mlflow_run(self, epochs=10, batch_size=64):
        experiment_name = "LinearRegression"
        experiment_id = mlflow.create_experiment(experiment_name + str(uuid.uuid4()))
        with mlflow.start_run(experiment_id=experiment_id) as run:
            sleep(5)
            mlflow.log_params({"number_epochs": epochs})
            mlflow.log_params({"batch_size": batch_size})
            # Actual training code would come here
            self.logger.debug("\nTrained model")
            mlflow.log_metric("loss", np.random.random())
        run_data = TestMLFlow.interceptor.dao.get_run_data(run.info.run_uuid)
        assert run_data.task_id == run.info.run_uuid
        return run.info.run_uuid

    def test_get_runs(self):
        runs = TestMLFlow.interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run in runs:
            assert isinstance(run[0], str)
            self.logger.debug(run[0])

    def test_get_run_data(self):
        run_uuid = self.simple_mlflow_run()
        run_data = TestMLFlow.interceptor.dao.get_run_data(run_uuid)
        assert run_data.task_id == run_uuid

    def test_check_state_manager(self):
        TestMLFlow.interceptor.state_manager.reset()
        TestMLFlow.interceptor.state_manager.add_element_id("dummy-value")
        self.simple_mlflow_run()
        runs = TestMLFlow.interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run_tuple in runs:
            run_uuid = run_tuple[0]
            assert isinstance(run_uuid, str)
            if not TestMLFlow.interceptor.state_manager.has_element_id(run_uuid):
                self.logger.debug(f"We need to intercept {run_uuid}")
                TestMLFlow.interceptor.state_manager.add_element_id(run_uuid)

    def test_observer_and_consumption(self):
        assert TestMLFlow.interceptor is not None
        with Flowcept(TestMLFlow.interceptor):
            run_uuid = self.simple_mlflow_run()
            sleep(5)
        print(run_uuid)
        assert evaluate_until(
            lambda: self.interceptor.state_manager.has_element_id(run_uuid),
        )

        assert assert_by_querying_tasks_until(
            {"task_id": run_uuid},
        )

    @unittest.skip("Skipping this test as we need to debug it further.")
    def test_multiple_tasks(self):
        run_ids = []
        with Flowcept(self.interceptor):
            for i in range(1, 10):
                run_ids.append(self.simple_mlflow_run(epochs=i * 10, batch_size=i * 2))
                sleep(3)

        for run_id in run_ids:
            # assert evaluate_until(
            #     lambda: self.interceptor.state_manager.has_element_id(run_id),
            # )

            assert assert_by_querying_tasks_until(
                {"task_id": run_id},
                max_trials=60,
                max_time=120,
            )


if __name__ == "__main__":
    unittest.main()
