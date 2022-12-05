from dataclasses import dataclass
from typing import List

from flowcept.flowceptor.plugins.base_settings_dataclasses import BaseSettings


@dataclass
class TensorboardSettings(BaseSettings):

    file_path: str
    log_tags: List[str]
    log_metrics: List[str]
    kind = "tensorboard"
    observer_type = "file"
    observer_subtype = "binary"
    watch_interval_sec: int
    redis_port: int
    redis_host: str
