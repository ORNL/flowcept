import abc
from dataclasses import dataclass
from typing import Any


@dataclass
class KeyValue:
    key: str
    value: Any


@dataclass
class BaseSettings(abc.ABC):

    key: str
    kind: str
    observer_type: str
    observer_subtype: str
