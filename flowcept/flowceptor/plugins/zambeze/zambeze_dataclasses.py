from dataclasses import dataclass
from typing import List, Dict

from flowcept.flowceptor.plugins.base_settings_dataclasses import (
    BaseSettings,
    KeyValue,
)


@dataclass
class ZambezeMessage:

    name: str
    activity_id: str
    campaign_id: str
    origin_agent_id: str
    files: List[str]
    command: str
    activity_status: str
    arguments: List[str]
    kwargs: Dict
    depends_on: List[str]


@dataclass
class ZambezeSettings(BaseSettings):

    host: str
    port: int
    queue_name: str
    key_values_to_filter: List[KeyValue]
    keys_to_intercept: List[str]
    kind = "zambeze"
    observer_type = "message_broker"
    observer_subtype = "rabbit_mq"
