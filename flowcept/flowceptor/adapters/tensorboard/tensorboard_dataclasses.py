from dataclasses import dataclass
from typing import List

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class TensorboardSettings(BaseSettings):
    file_path: str
    log_tags: List[str]
    log_metrics: List[str]
    watch_interval_sec: int
    redis_port: int
    redis_host: str
    kind = "tensorboard"

    def __post_init__(self):
        self.observer_type = "file"
        self.observer_subtype = "binary"
