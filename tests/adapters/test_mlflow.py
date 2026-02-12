import os
import unittest
import os
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

    def test_observer_and_consumption_one(self):
        self._test_observer_and_consumption()

    def test_observer_and_consumption_loop(self):
        n_runs = int(os.getenv("TEST_MLFLOW_OBSERVER_CONSUMPTION_LOOPS", "2"))
        for idx in range(n_runs):
            self.logger.warning(f"test_observer_and_consumption start iteration={idx + 1}/{n_runs}")
            self._test_observer_and_consumption()
            self.logger.warning(f"test_observer_and_consumption end iteration={idx + 1}/{n_runs}")

    def _test_observer_and_consumption(self):
        self.logger.warning(f"test_observer_and_consumption DB_FLUSH_MODE={configs.DB_FLUSH_MODE}")
        if configs.DB_FLUSH_MODE != "online":
            msg = (
                "Skipping assertion in test_observer_and_consumption because "
                f"DB_FLUSH_MODE is '{configs.DB_FLUSH_MODE}', expected 'online'."
            )
            self.logger.warning(msg)
            return

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

    def _reset_kafka_topic(self):
        if configs.MQ_TYPE != "kafka":
            return
        from confluent_kafka.admin import AdminClient, NewTopic

        topic = configs.MQ_CHANNEL
        admin = AdminClient({"bootstrap.servers": f"{configs.MQ_HOST}:{configs.MQ_PORT}"})
        delete_futures = admin.delete_topics([topic], operation_timeout=10)
        try:
            delete_futures[topic].result()
        except Exception:
            pass
        create_futures = admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)])
        try:
            create_futures[topic].result()
        except Exception:
            pass
        for _ in range(10):
            try:
                if topic in admin.list_topics(timeout=5).topics:
                    break
            except Exception:
                pass
            sleep(0.5)

    def _test_observer_and_consumption_race(self, n_noisy_messages=300, n_runs=3):
        """Stress MLflow consumption under a heavy Kafka backlog."""
        if configs.DB_FLUSH_MODE != "online":
            self.skipTest("DB_FLUSH_MODE is not online.")
        if configs.MQ_TYPE == "kafka":
            self._reset_kafka_topic()
        from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
        from threading import Thread, Event

        mq = MQDao.build()
        stop_noise = Event()

        def _noise_publisher():
            i = 0
            while i < n_noisy_messages and not stop_noise.is_set():
                # Seed a backlog so the consumer must handle noise while MLflow events arrive.
                mq.send_message({"type": "task", "task_id": f"backlog_{i}"})
                sleep(0.0001)
                i += 1

        _noise_publisher()

        run_uuids = []
        noise_thread = Thread(target=_noise_publisher, daemon=True)
        with Flowcept(interceptors="mlflow") as f:
            noise_thread.start()
            file_path = f._interceptor_instances[0].settings.file_path
            for _ in range(n_runs):
                run_uuid = self.simple_mlflow_run(file_path, epochs=2, batch_size=8)
                run_uuids.append(run_uuid)
            # Stop noise before Flowcept shutdown to avoid producer-vs-stop races
            # that can drop late messages unrelated to MLflow interception itself.
            stop_noise.set()
            noise_thread.join()
        try:
            for run_uuid in run_uuids:
                assert assert_by_querying_tasks_until(
                    {"task_id": run_uuid},
                )
        finally:
            if run_uuids:
                self.__class__.created_task_ids.extend(run_uuids)
                self._cleanup_task_ids(run_uuids)

    def test_observer_and_consumption_race_one(self):
        self._test_observer_and_consumption_race()

    def test_observer_and_consumption_race_loop(self):
        n_runs = 2
        for idx in range(n_runs):
            self.logger.warning(f"_test_observer_and_consumption_race start iteration={idx + 1}/{n_runs}")
            self._test_observer_and_consumption_race()
            self.logger.warning(f"_test_observer_and_consumption_race end iteration={idx + 1}/{n_runs}")

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
