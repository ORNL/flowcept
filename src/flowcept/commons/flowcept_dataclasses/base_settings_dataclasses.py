"""Base settings module."""

import abc
from dataclasses import dataclass, field
from typing import Optional, Any


@dataclass
class KeyValue:
    """Key value class."""

    key: str
    value: Any


@dataclass
class BaseSettings(abc.ABC):
    """Base settings class."""

    key: str
    kind: str
    observer_type: str = field(init=False)
    observer_subtype: Optional[str] = field(init=False)
