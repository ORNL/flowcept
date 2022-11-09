from dataclasses import dataclass
from typing import Any, List


@dataclass
class KeyValuesToFilter:
    key: str
    value: Any


@dataclass
class MQSettings:

    host: str
    port: int
    queue_name: str
    key_values_to_filter: List[KeyValuesToFilter]
    keys_to_intercept: List[str]
    type: str = 'message_broker'
    subtype: str = 'mq'




