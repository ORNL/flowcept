# Make sure you run `pip install flowcept[mlflow]` first.
import os
import uuid
from time import sleep
import mlflow

from flowcept import Flowcept
from flowcept.configs import settings


if __name__ == "__main__":
    # Starting the interceptor
    file_path = settings["adapters"]["mlflow"]["file_path"]
    print(f"SQLITE DB path: {file_path}")

    # Clean up previous runs if they exist
    if os.path.exists(file_path):
        os.remove(file_path)
    with open(file_path, "w") as f:
        f.write("")
    sleep(1)
    mlflow.set_tracking_uri(f"sqlite:///{file_path}")
    mlflow.delete_experiment(mlflow.create_experiment("starter"))
    sleep(1)

    # Starting the workflow
    with Flowcept("mlflow"):
        experiment_name = "experiment_test"
        experiment_id = mlflow.create_experiment(experiment_name + str(uuid.uuid4()))
        with mlflow.start_run(experiment_id=experiment_id) as run:
            mlflow.log_params({"param1": 1})
            mlflow.log_params({"param2": 2})
            mlflow.log_metric("metric1", 10)
            run_id = run.info.run_id
    task = Flowcept.db.query(filter={"task_id": run_id})[0]
    assert task["status"] == "FINISHED"
    assert "param1" in task["used"]
    assert "metric1" in task["generated"]
