from dataclasses import dataclass
from typing import List

from flowcept.flowceptor.plugins.base_settings_dataclasses import BaseSettings


@dataclass
class DaskSettings(BaseSettings):

    redis_port: int
    redis_host: str
    kind = "dask"
    observer_type = "outsourced"
    observer_subtype = None
