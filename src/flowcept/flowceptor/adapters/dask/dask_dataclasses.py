"""Dataclasses module."""

from dataclasses import dataclass

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class DaskSettings(BaseSettings):
    """Dask settings."""

    redis_port: int
    redis_host: str
    worker_should_get_input: bool
    worker_should_get_output: bool
    scheduler_should_get_input: bool
    scheduler_create_timestamps: bool
    worker_create_timestamps: bool
    kind = "dask"

    def __post_init__(self):
        """Set attributes after init."""
        self.observer_type = "outsourced"
        self.observer_subtype = None
