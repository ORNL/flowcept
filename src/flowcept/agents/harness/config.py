"""Runtime configuration for the harness capture path.

Every knob is an environment variable so that it can be set from a harness
settings file, a plugin ``userConfig``, or a shell profile without needing a
config file on disk. Nothing here imports flowcept.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PREFIX = "FLOWCEPT_HARNESS_"

#: Content capture modes for potentially large tool payloads.
CONTENT_FULL = "full"
CONTENT_SUMMARY = "summary"
CONTENT_NONE = "none"
CONTENT_MODES = (CONTENT_FULL, CONTENT_SUMMARY, CONTENT_NONE)


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(ENV_PREFIX + name, default)


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def default_home() -> Path:
    """Return the base directory holding session state and buffers."""
    explicit = _env("HOME")
    if explicit:
        return Path(explicit).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "flowcept-harness"
    return Path.home() / ".flowcept" / "harness"


# Deliberately a plain class rather than a dataclass: importing `dataclasses`
# costs ~80ms (it pulls in `inspect` and `ast`), which is a third of the wall
# time of a hook process that otherwise does almost nothing.
class Config:
    """Resolved capture configuration."""

    __slots__ = (
        "buffer_dir",
        "campaign_id",
        "campaign_scope",
        "capture_prompts",
        "capture_telemetry",
        "capture_tool_results",
        "content_mode",
        "debug",
        "enabled",
        "home",
        "max_str",
        "online",
        "redact",
        "source_agent_id",
        "timeout_ms",
    )

    def __init__(
        self,
        enabled: bool = True,
        home: Path | None = None,
        #: Where records are appended. One JSONL file per session keeps
        #: concurrent sessions from interleaving and makes ingest cheap.
        buffer_dir: Path | None = None,
        #: Group every session under the same project into one campaign.
        campaign_id: str | None = None,
        campaign_scope: str = "project",  # project | global | none
        #: Max characters kept for any single captured string.
        max_str: int = 4000,
        #: How to treat file contents in Write/Edit-style tool inputs.
        content_mode: str = CONTENT_SUMMARY,
        #: Redact secret-looking keys and obvious credential literals.
        redact: bool = True,
        capture_telemetry: bool = False,
        capture_prompts: bool = True,
        capture_tool_results: bool = True,
        #: Link every emitted turn/tool/LLM task back to a task or agent from
        #: another capture system (stamped as ``source_agent_id``). A
        #: ``flowcept_source_agent_id`` hook-payload key wins over this.
        source_agent_id: str | None = None,
        #: Publish to the Flowcept MQ in addition to the JSONL buffer.
        online: bool = False,
        #: Hard ceiling on hook wall time.
        timeout_ms: int = 2000,
        #: Log capture failures instead of staying silent.
        debug: bool = False,
    ):
        self.enabled = enabled
        self.home = home if home is not None else default_home()
        self.buffer_dir = buffer_dir
        self.campaign_id = campaign_id
        self.campaign_scope = campaign_scope
        self.max_str = max_str
        self.content_mode = content_mode
        self.redact = redact
        self.capture_telemetry = capture_telemetry
        self.capture_prompts = capture_prompts
        self.capture_tool_results = capture_tool_results
        self.source_agent_id = source_agent_id
        self.online = online
        self.timeout_ms = timeout_ms
        self.debug = debug

    def __repr__(self) -> str:
        """Return a debug representation listing every configured field."""
        fields = ", ".join(f"{name}={getattr(self, name)!r}" for name in self.__slots__)
        return f"Config({fields})"

    @property
    def sessions_dir(self) -> Path:
        """Directory holding per-session state files."""
        return self.home / "sessions"

    @property
    def buffers_dir(self) -> Path:
        """Directory holding JSONL buffer files, honoring any override."""
        return self.buffer_dir or (self.home / "buffers")

    @property
    def log_path(self) -> Path:
        """Path of the harness debug log file."""
        return self.home / "harness.log"

    def buffer_path(self, workflow_id: str) -> Path:
        """Return the JSONL buffer file path for ``workflow_id``."""
        return self.buffers_dir / f"{workflow_id}.jsonl"

    def state_path(self, workflow_id: str) -> Path:
        """Return the session state file path for ``workflow_id``."""
        return self.sessions_dir / f"{workflow_id}.json"


def load_config() -> Config:
    """Build a :class:`Config` from the environment."""
    content_mode = (_env("CONTENT", CONTENT_SUMMARY) or CONTENT_SUMMARY).strip().lower()
    if content_mode not in CONTENT_MODES:
        content_mode = CONTENT_SUMMARY

    buffer_dir = _env("BUFFER_DIR")
    return Config(
        enabled=_env_bool("ENABLED", True),
        home=default_home(),
        buffer_dir=Path(buffer_dir).expanduser() if buffer_dir else None,
        campaign_id=_env("CAMPAIGN_ID"),
        campaign_scope=(_env("CAMPAIGN_SCOPE", "project") or "project").strip().lower(),
        max_str=_env_int("MAX_STR", 4000),
        content_mode=content_mode,
        redact=_env_bool("REDACT", True),
        capture_telemetry=_env_bool("TELEMETRY", False),
        capture_prompts=_env_bool("CAPTURE_PROMPTS", True),
        capture_tool_results=_env_bool("CAPTURE_TOOL_RESULTS", True),
        source_agent_id=_env("SOURCE_AGENT_ID"),
        online=_env_bool("ONLINE", False),
        timeout_ms=_env_int("TIMEOUT_MS", 2000),
        debug=_env_bool("DEBUG", False),
    )
