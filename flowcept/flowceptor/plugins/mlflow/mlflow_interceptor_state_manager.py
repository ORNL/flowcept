from redis import Redis
from flowcept.flowceptor.plugins.settings_data_classes import (
    MLFlowSettings,
)


class MLFlowInterceptorStateManager:

    _SET_NAME = "runs"

    def __init__(self, mlflow_settings: MLFlowSettings):
        self._db = Redis(
            host=mlflow_settings.redis_host,
            port=mlflow_settings.redis_port,
            db=0,
        )

    def clear_set(self):
        self._db.delete(MLFlowInterceptorStateManager._SET_NAME)

    def add_run(self, run_id: str):
        self._db.sadd(MLFlowInterceptorStateManager._SET_NAME, run_id)

    def has_run(self, run_id):
        return self._db.sismember(
            MLFlowInterceptorStateManager._SET_NAME, run_id
        )
