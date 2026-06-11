"""Dataclasses module."""

from dataclasses import dataclass

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class DaskSettings(BaseSettings):
    """Dask settings."""

    key: str = "dask"
    kind: str = "dask"
    worker_should_get_input: bool = True
    worker_should_get_output: bool = True
    scheduler_should_get_input: bool = True
    scheduler_create_timestamps: bool = True
    worker_create_timestamps: bool = False

    def __post_init__(self):
        """Set attributes after init."""
        self.observer_type = "outsourced"
        self.observer_subtype = None
