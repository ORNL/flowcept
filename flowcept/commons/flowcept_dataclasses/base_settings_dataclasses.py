import abc
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class KeyValue:
    key: str
    value: Any


@dataclass
class BaseSettings(abc.ABC):
    key: str
    kind: str
    enrich_messages: bool
    observer_type: str = field(init=False)
    observer_subtype: Optional[str] = field(init=False)
