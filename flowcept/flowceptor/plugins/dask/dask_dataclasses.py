from dataclasses import dataclass

from flowcept.flowceptor.plugins.base_settings_dataclasses import BaseSettings


@dataclass
class DaskSettings(BaseSettings):

    redis_port: int
    redis_host: str
    kind = "dask"

    def __post_init__(self):
        self.observer_type = "outsourced"
        self.observer_subtype = None
