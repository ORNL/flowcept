"""Base settings module."""

import abc
import dataclasses
import os
from dataclasses import dataclass, field
from pathlib import Path
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

    def save_settings(self):
        """Save this adapter's settings into ~/.flowcept/settings.yaml."""
        from omegaconf import OmegaConf

        settings_path_env = os.getenv("FLOWCEPT_SETTINGS_PATH", None)
        settings_path = Path(settings_path_env) if settings_path_env else Path.home() / ".flowcept" / "settings.yaml"
        cfg = OmegaConf.load(settings_path) if settings_path.exists() else OmegaConf.create({})
        adapter_key = self.key
        d = dataclasses.asdict(self)
        for runtime_field in ("key", "observer_type", "observer_subtype"):
            d.pop(runtime_field, None)
        OmegaConf.update(cfg, f"adapters.{adapter_key}", d, merge=False)
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        OmegaConf.save(cfg, settings_path)
