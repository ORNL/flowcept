"""Dataclasses module."""

from dataclasses import dataclass, field
from typing import List

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class MLFlowSettings(BaseSettings):
    """MLFlow settings."""

    key: str = "mlflow"
    kind: str = "mlflow"
    file_path: str = "mlflow.db"
    log_params: List[str] = field(default_factory=lambda: ["*"])
    log_metrics: List[str] = field(default_factory=lambda: ["*"])
    watch_interval_sec: int = 1

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
