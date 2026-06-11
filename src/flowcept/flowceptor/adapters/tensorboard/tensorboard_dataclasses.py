"""Tensorboard dataclasses module."""

from dataclasses import dataclass, field
from typing import List

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class TensorboardSettings(BaseSettings):
    """Tensorboard settings."""

    key: str = "tensorboard"
    kind: str = "tensorboard"
    file_path: str = "tensorboard_events"
    log_tags: List[str] = field(default_factory=lambda: ["scalars", "hparams", "tensors"])
    log_metrics: List[str] = field(default_factory=lambda: ["accuracy"])
    watch_interval_sec: int = 5

    def __post_init__(self):
        """Set attributes after init."""
        self.observer_type = "file"
        self.observer_subtype = "binary"
