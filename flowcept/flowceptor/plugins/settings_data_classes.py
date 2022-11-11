from dataclasses import dataclass
from typing import Any, List


@dataclass
class KeyValuesToFilter:
    key: str
    value: Any


@dataclass
class ZambezeSettings:

    host: str
    port: int
    queue_name: str
    key_values_to_filter: List[KeyValuesToFilter]
    keys_to_intercept: List[str]
    kind: str = "zambeze"
    observer_type: str = "message_broker"
    observer_subtype: str = "rabbit_mq"


@dataclass
class MLFlowSettings:

    file_path: str
    log_params: List[str]
    log_metrics: List[str]
    watch_interval_sec: int
    kind: str = "mlflow"
    observer_type: str = "db"
    observer_subtype: str = "sqlite"
