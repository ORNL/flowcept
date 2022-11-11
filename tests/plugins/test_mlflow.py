import unittest
import threading
import time

from flowcept.flowcept_consumer.consumer import consume_intercepted_messages
from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor import (
    MLFlowInterceptor,
)


class TestMLFlow(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestMLFlow, self).__init__(*args, **kwargs)
        self.interceptor = MLFlowInterceptor("mlflow1")

        threading.Thread(target=self.interceptor.observe, daemon=True).start()
        threading.Thread(
            target=consume_intercepted_messages, daemon=True
        ).start()
        time.sleep(3)

    def test_mlflow(self):
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
        with mlflow.start_run(experiment_id=experiment_id):
            mlflow.log_params({"number_epochs": 10})
            print("\nTrained model")
            mlflow.log_metric("loss", 0.04)

        time.sleep(3)


if __name__ == "__main__":
    unittest.main()
