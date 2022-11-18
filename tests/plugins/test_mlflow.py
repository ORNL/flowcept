import unittest
import threading
import time

from flowcept.flowcept_consumer.consumer import (
    consume_intercepted_messages,
)
from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor import (
    MLFlowInterceptor,
)


class TestMLFlow(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestMLFlow, self).__init__(*args, **kwargs)
        self.interceptor = MLFlowInterceptor()

    def test_pure_run_mlflow(self):
        import uuid
        import mlflow

        # from mlflow.tracking import MlflowClient
        # client = MlflowClient()
        mlflow.set_tracking_uri(
            f"sqlite:///" f"{self.interceptor.settings.file_path}"
        )
        experiment_name = "LinearRegression"
        experiment_id = mlflow.create_experiment(
            experiment_name + str(uuid.uuid4())
        )
        with mlflow.start_run(experiment_id=experiment_id) as run:
            mlflow.log_params({"number_epochs": 10})
            mlflow.log_params({"batch_size": 64})

            print("\nTrained model")
            mlflow.log_metric("loss", 0.04)

            return run.info.run_uuid

    def test_get_runs(self):
        runs = self.interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run in runs:
            assert type(run[0]) == str
            print(run[0])

    def test_get_run_data(self):
        run_uuid = self.test_pure_run_mlflow()
        run_data = self.interceptor.dao.get_run_data(run_uuid)
        assert run_data.run_uuid == run_uuid

    def test_check_state_manager(self):
        self.interceptor.state_manager.clear_set()
        self.interceptor.state_manager.add_element_id("dummy-value")
        self.test_pure_run_mlflow()
        runs = self.interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run_tuple in runs:
            run_uuid = run_tuple[0]
            assert type(run_uuid) == str
            if not self.interceptor.state_manager.has_element_id(run_uuid):
                print(f"We need to intercept {run_uuid}")
                self.interceptor.state_manager.add_element_id(run_uuid)

    def _init_mlflow_consumption(self):
        threading.Thread(target=self.interceptor.observe, daemon=True).start()
        threading.Thread(
            target=consume_intercepted_messages, daemon=True
        ).start()
        time.sleep(3)

    def test_mlflow_observer_and_consumption(self):
        self._init_mlflow_consumption()
        run_uuid = self.test_pure_run_mlflow()
        time.sleep(5)
        assert self.interceptor.state_manager.has_element_id(run_uuid) is True


if __name__ == "__main__":
    unittest.main()
