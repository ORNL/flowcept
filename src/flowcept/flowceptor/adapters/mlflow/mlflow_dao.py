"""DAO module."""

from typing import List
from sqlalchemy.engine import Row, create_engine
from sqlalchemy import text
from textwrap import dedent

from flowcept.commons import singleton
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.mlflow.mlflow_dataclasses import (
    RunData,
    MLFlowSettings,
)


@singleton
class MLFlowDAO:
    """DAO class."""

    _LIMIT = 10
    # TODO: This should not at all be hard coded.
    # This value needs to be greater than the amount of
    # runs inserted in the Runs table at each data observation

    def __init__(self, mlflow_settings: MLFlowSettings):
        self._engine = MLFlowDAO._get_db_engine(mlflow_settings.file_path)
        self.logger = FlowceptLogger()

    @staticmethod
    def _get_db_engine(sqlite_file):
        try:
            db_uri = f"sqlite:///{sqlite_file}"
            engine = create_engine(db_uri)
            return engine
        except Exception:
            raise Exception(f"Could not create DB engine with uri: {db_uri}")

    def get_finished_run_uuids(self) -> List[Row]:
        """Get the finished run."""
        sql = text(
            dedent(
                f"""
            SELECT run_uuid
            FROM
                runs
            WHERE
                status = 'FINISHED'
            ORDER BY end_time DESC
            LIMIT {MLFlowDAO._LIMIT}
            """
            )
        )
        try:
            conn = self._engine.connect()
            results = conn.execute(sql).fetchall()
            return results
        except Exception as e:
            self.logger.debug(str(e))
            return None
        finally:
            conn.close()

    def get_run_data(self, run_uuid: str) -> RunData:
        """Get the run data."""
        # TODO: consider outer joins to get the run data even if there's
        #  no metric or param or if the task hasn't finished yet
        sql = text(
            dedent(
                f"""
            SELECT r.run_uuid, r.start_time, r.end_time, r.status,
               m.key as 'metric_key', m.value as 'metric_value',
               p.key as 'parameter_key', p.value as 'parameter_value'
            FROM
                runs AS r,
                metrics as m,
                params as p
            WHERE
                r.run_uuid = m.run_uuid AND
                m.run_uuid = p.run_uuid AND
                r.run_uuid = '{run_uuid}' AND
                r.status = 'FINISHED' 
            ORDER BY
                end_time DESC,
                metric_key, metric_value,
                parameter_key, parameter_value
            LIMIT 30
"""
            )
        )
        try:
            conn = self._engine.connect()
            result_set = conn.execute(sql).fetchall()
        except Exception as e:
            self.logger.exception(e)
            return None
        finally:
            conn.close()
        run_data_dict = {"used": {}, "generated": {}}
        for tuple_ in result_set:
            tuple_dict = tuple_._asdict()
            metric_key = tuple_dict.get("metric_key", None)
            metric_value = tuple_dict.get("metric_value", None)
            if metric_key and metric_value:
                if metric_key not in run_data_dict["generated"]:
                    run_data_dict["generated"][metric_key] = None
                run_data_dict["generated"][metric_key] = metric_value

            param_key = tuple_dict.get("parameter_key", None)
            param_value = tuple_dict.get("parameter_value", None)
            if param_key and param_value:
                if param_key not in run_data_dict["used"]:
                    run_data_dict["used"][param_key] = None
                run_data_dict["used"][param_key] = param_value

            run_data_dict["task_id"] = tuple_dict["run_uuid"]
            run_data_dict["start_time"] = tuple_dict["start_time"]
            run_data_dict["end_time"] = tuple_dict["end_time"]
            run_data_dict["status"] = tuple_dict["status"]
        try:
            run_data = RunData(**run_data_dict)
            return run_data
        except Exception as e:
            self.logger.warning(e)
            return None
