from sqlalchemy import create_engine
from flowcept.flowceptor.plugins.mlflow.mlflow_dataclasses import Run
from flowcept.flowceptor.plugins.settings_dataclasses import (
    MLFlowSettings,
)


class MLFlowDAO:

    _LIMIT = 10
    # TODO: This should not at all be hard coded.
    # This value needs to be greater than the amount of
    # runs inserted in the Runs table at each data observation

    def __init__(self, mlflow_settings: MLFlowSettings):
        self._engine = MLFlowDAO._get_db_engine(mlflow_settings.file_path)

    @staticmethod
    def _get_db_engine(sqlite_file):
        try:
            db_uri = f"sqlite:///{sqlite_file}"
            engine = create_engine(db_uri)
            return engine
        except Exception:
            raise Exception(f"Could not create DB engine with uri: {db_uri}")

    def get_runs(self):

        sql = (
            f"SELECT {Run.fields} FROM"
            f" runs ORDER BY end_time LIMIT {MLFlowDAO._LIMIT}"
        )
        conn = self._engine.connect()
        results = conn.execute(sql).fetchall()
        return results
