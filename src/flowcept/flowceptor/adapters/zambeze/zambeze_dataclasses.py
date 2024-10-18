"""Zambeze dataclass module."""

from dataclasses import dataclass
from typing import List, Dict

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
    KeyValue,
)


@dataclass
class ZambezeMessage:
    """Zambeze message."""

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
    """Zambeze settings."""

    host: str
    port: int
    queue_names: List[str]
    key_values_to_filter: List[KeyValue] = None
    kind = "zambeze"

    def __post_init__(self):
        """Set attributes after init."""
        self.observer_type = "message_broker"
        self.observer_subtype = "rabbit_mq"
