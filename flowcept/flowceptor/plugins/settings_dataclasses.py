import abc
from dataclasses import dataclass
from typing import Any, List


@dataclass
class KeyValue:
    key: str
    value: Any


@dataclass
class AbstractSettings(abc.ABC):

    key: str
    kind: str
    observer_type: str
    observer_subtype: str


@dataclass
class ZambezeSettings(AbstractSettings):

    host: str
    port: int
    queue_name: str
    key_values_to_filter: List[KeyValue]
    keys_to_intercept: List[str]
    kind = "zambeze"
    observer_type = "message_broker"
    observer_subtype = "rabbit_mq"


@dataclass
class MLFlowSettings(AbstractSettings):

    file_path: str
    log_params: List[str]
    log_metrics: List[str]
    watch_interval_sec: int
    redis_port: int
    redis_host: str
    kind = "mlflow"
    observer_type = "db"
    observer_subtype = "sqlite"
