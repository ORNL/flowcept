import unittest
import uuid
from time import sleep
import numpy as np
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept import Flowcept
from flowcept import configs
from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO


class TestMLFlow(unittest.TestCase):
    created_task_ids = []

    def __init__(self, *args, **kwargs):
        super(TestMLFlow, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    def simple_mlflow_run(self, mlflow_path, epochs=10, batch_size=64):
        import mlflow
        mlflow.set_tracking_uri(f"sqlite:///{mlflow_path}")
        experiment_id = mlflow.create_experiment("LinearRegression" + str(uuid.uuid4()))
        with mlflow.start_run(experiment_id=experiment_id) as run:
            mlflow.log_params({"number_epochs": epochs})
            mlflow.log_params({"batch_size": batch_size})
            sleep(0.1)
            # Actual training code would come here
            self.logger.debug("\nTrained model")
            mlflow.log_metric("loss", np.random.random())
        return run.info.run_id

    def _cleanup_task_ids(self, task_ids):
        dao = DocumentDBDAO.get_instance(create_indices=False)
        dao.delete_task_keys("task_id", task_ids)

    def test_get_runs(self):
        run_uuid = None
        with Flowcept("mlflow") as f:
            file_path = f._interceptor_instances[0].settings.file_path
            run_uuid = self.simple_mlflow_run(file_path)
            runs = f._interceptor_instances[0].dao.get_finished_run_uuids()
        assert runs is not None and len(runs) > 0
        for run in runs:
            assert isinstance(run[0], str)
            self.logger.debug(run[0])
        if run_uuid is not None:
            self.__class__.created_task_ids.append(run_uuid)
            self._cleanup_task_ids([run_uuid])

    def test_get_run_data(self):
        run_uuid = None
        with Flowcept("mlflow") as f:
            file_path = f._interceptor_instances[0].settings.file_path
            run_uuid = self.simple_mlflow_run(file_path)
            run_data = f._interceptor_instances[0].dao.get_run_data(run_uuid)

        assert run_data.task_id == run_uuid
        if run_uuid is not None:
            self.__class__.created_task_ids.append(run_uuid)
            self._cleanup_task_ids([run_uuid])

    def test_check_state_manager(self):
        run_uuid = None
        with Flowcept("mlflow") as f:
            interceptor = f._interceptor_instances[0]
            file_path = interceptor.settings.file_path
            interceptor.state_manager.reset()
            interceptor.state_manager.add_element_id("dummy-value")

            run_uuid = self.simple_mlflow_run(file_path)
        runs = interceptor.dao.get_finished_run_uuids()
        assert len(runs) > 0
        for run_tuple in runs:
            run_uuid = run_tuple[0]
            assert isinstance(run_uuid, str)
            if not interceptor.state_manager.has_element_id(run_uuid):
                self.logger.debug(f"We need to intercept {run_uuid}")
                interceptor.state_manager.add_element_id(run_uuid)
        if run_uuid is not None:
            self.__class__.created_task_ids.append(run_uuid)
            self._cleanup_task_ids([run_uuid])

    def test_observer_and_consumption(self):
        self.logger.warning(f"test_observer_and_consumption DB_FLUSH_MODE={configs.DB_FLUSH_MODE}")
        if configs.DB_FLUSH_MODE != "online":
            msg = (
                "Skipping assertion in test_observer_and_consumption because "
                f"DB_FLUSH_MODE is '{configs.DB_FLUSH_MODE}', expected 'online'."
            )
            self.logger.warning(msg)
            return
        run_uuid = None
        with Flowcept(interceptors="mlflow") as f:
            file_path = f._interceptor_instances[0].settings.file_path
            run_uuid = self.simple_mlflow_run(file_path)
        print(run_uuid)
        try:
            assert assert_by_querying_tasks_until(
                {"task_id": run_uuid},
            )
        finally:
            if run_uuid is not None:
                self.__class__.created_task_ids.append(run_uuid)
                self._cleanup_task_ids([run_uuid])

    @unittest.skip("Skipping this test as we need to debug it further.")
    def test_multiple_tasks(self):
        run_ids = []
        with Flowcept("mlflow") as f:
            file_path = f._interceptor_instances[0].settings.file_path
            for i in range(1, 10):
                run_ids.append(self.simple_mlflow_run(file_path, epochs=i * 10, batch_size=i * 2))
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

    @classmethod
    def tearDownClass(cls):
        if cls.created_task_ids:
            dao = DocumentDBDAO.get_instance(create_indices=False)
            dao.delete_task_keys("task_id", cls.created_task_ids)
        Flowcept.db.close()


if __name__ == "__main__":
    unittest.main()
