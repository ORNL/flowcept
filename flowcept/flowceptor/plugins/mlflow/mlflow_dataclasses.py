from dataclasses import dataclass
from typing import List

from flowcept.flowceptor.plugins.base_settings_dataclasses import BaseSettings


@dataclass
class MLFlowSettings(BaseSettings):

    file_path: str
    log_params: List[str]
    log_metrics: List[str]
    watch_interval_sec: int
    redis_port: int
    redis_host: str
    kind = "mlflow"
    observer_type = "file"
    observer_subtype = "sqlite"


@dataclass
class RunData:

    run_uuid: str
    start_time: int
    end_time: int
    metrics: dict
    parameters: dict
    status: str
