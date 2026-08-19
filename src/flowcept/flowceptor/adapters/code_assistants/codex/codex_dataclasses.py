"""Codex adapter settings."""

from dataclasses import dataclass

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
)


@dataclass
class CodexSettings(BaseSettings):
    """Codex session log settings."""

    key: str = "codex"
    kind: str = "codex"
    file_path: str = "codex_events.jsonl"
    watch_interval_sec: int = 1
    recursive: bool = True
    include_developer_messages: bool = True
    include_reasoning: bool = True
    declared_provenance_enabled: bool = False

    def __post_init__(self):
        """Set runtime observer metadata."""
        self.observer_type = "file"
        self.observer_subtype = "jsonl"
