"""Dataclasses module."""

from dataclasses import dataclass
from typing import List

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class MLFlowSettings(BaseSettings):
    """MLFlow settings."""

    file_path: str
    log_params: List[str]
    log_metrics: List[str]
    watch_interval_sec: int
    redis_port: int
    redis_host: str
    kind = "mlflow"

    def __post_init__(self):
        """Set attributes after init."""
        self.observer_type = "file"
        self.observer_subtype = "sqlite"


@dataclass
class RunData:
    """Run data class."""

    task_id: str
    start_time: int
    end_time: int
    used: dict
    generated: dict
    status: str
