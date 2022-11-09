import pytest

from flowcept.flowceptor.plugins.utils import get_mq_settings

MLFLOW_SETTINGS = get_mq_settings('mlflow')




# @pytest.fixture(scope="session", autouse=True)
# def redis_consumer_thread():
#     from flowcept.flowcept_consumer.consumer import main as FlowceptConsumer
#     t = threading.Thread(target=FlowceptConsumer, daemon=True)
#     t.start()
#     return t
#

@pytest.mark.unit
def test_mlflow():#(redis_consumer_thread=None):
    import uuid
    import mlflow
    from mlflow.tracking import MlflowClient
    client = MlflowClient()
    mlflow.set_tracking_uri("sqlite:///renan.db")

    experiment_name = 'LinearRegression'
    experiment_id = mlflow.create_experiment(experiment_name + str(uuid.uuid4()))
    with mlflow.start_run(experiment_id=experiment_id) as run:
        mlflow.log_params({"number_epochs": 10})
        print("trained model")
        mlflow.log_metric('loss', 0.04)
