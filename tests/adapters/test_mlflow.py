import unittest
from time import sleep

from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept import MLFlowInterceptor, FlowceptConsumerAPI
from flowcept.commons.utils import (
    assert_by_querying_task_collections_until,
    evaluate_until,
)


class TestMLFlow(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestMLFlow, self).__init__(*args, **kwargs)
        self.interceptor = MLFlowInterceptor()
        self.logger = FlowceptLogger()

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

            self.logger.debug("\nTrained model")
            mlflow.log_metric("loss", 0.04)

            return run.info.run_uuid

    def test_pure_run_mlflow_no_ctx_mgr(self):
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
        run = mlflow.start_run(experiment_id=experiment_id)
        mlflow.log_params({"number_epochs": 10})
        mlflow.log_params({"batch_size": 64})
        self.logger.debug("\nTrained model")
        mlflow.log_metric("loss", 0.04)
        mlflow.end_run()
        return run.info.run_uuid

    def test_get_runs(self):
        runs = self.interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run in runs:
            assert type(run[0]) == str
            self.logger.debug(run[0])

    def test_get_run_data(self):
        run_uuid = self.test_pure_run_mlflow()
        run_data = self.interceptor.dao.get_run_data(run_uuid)
        assert run_data.task_id == run_uuid

    def test_check_state_manager(self):
        self.interceptor.state_manager.reset()
        self.interceptor.state_manager.add_element_id("dummy-value")
        self.test_pure_run_mlflow()
        runs = self.interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run_tuple in runs:
            run_uuid = run_tuple[0]
            assert type(run_uuid) == str
            if not self.interceptor.state_manager.has_element_id(run_uuid):
                self.logger.debug(f"We need to intercept {run_uuid}")
                self.interceptor.state_manager.add_element_id(run_uuid)

    def test_observer_and_consumption(self):
        with FlowceptConsumerAPI(self.interceptor):
            run_uuid = self.test_pure_run_mlflow()
            sleep(5)

        assert evaluate_until(
            lambda: self.interceptor.state_manager.has_element_id(run_uuid)
        )
        assert assert_by_querying_task_collections_until(
            DocumentDBDao(),
            {"task_id": run_uuid},
        )


if __name__ == "__main__":
    unittest.main()
