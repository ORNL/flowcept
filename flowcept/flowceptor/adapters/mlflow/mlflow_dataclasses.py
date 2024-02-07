from dataclasses import dataclass
from typing import List

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class MLFlowSettings(BaseSettings):
    file_path: str
    log_params: List[str]
    log_metrics: List[str]
    watch_interval_sec: int
    redis_port: int
    redis_host: str
    kind = "mlflow"

    def __post_init__(self):
        self.observer_type = "file"
        self.observer_subtype = "sqlite"


@dataclass
class RunData:
    task_id: str
    start_time: int
    end_time: int
    used: dict
    generated: dict
    status: str
