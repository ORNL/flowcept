"""Per-session state shared across independent hook processes.

A harness fires each lifecycle event in its own process, and parallel tool
calls mean several of those processes can run at the same instant. State is
therefore a small JSON file guarded by an advisory lock, always read-modify-
written inside the lock so concurrent ``PostToolUse`` hooks cannot clobber each
other.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

try:  # POSIX
    import fcntl

    _HAVE_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
    _HAVE_FCNTL = False

try:  # Windows
    import msvcrt

    _HAVE_MSVCRT = True
except ImportError:
    msvcrt = None  # type: ignore[assignment]
    _HAVE_MSVCRT = False


#: Pending tool calls older than this are dropped: their PostToolUse never
#: arrived (the harness crashed, or the call was interrupted).
PENDING_TTL_SECONDS = 6 * 60 * 60
MAX_PENDING = 512


@contextmanager
def file_lock(path: Path, timeout: float = 5.0) -> Iterator[None]:
    """Acquire an exclusive advisory lock on ``path`` (``path`` need not exist)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    deadline = time.monotonic() + timeout
    try:
        while True:
            try:
                if _HAVE_FCNTL:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                elif _HAVE_MSVCRT:  # pragma: no cover - Windows
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    # Never block the harness on a stuck lock: proceed unlocked
                    # and accept the small risk of a lost concurrent update.
                    break
                time.sleep(0.01)
        yield
    finally:
        try:
            if _HAVE_FCNTL:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif _HAVE_MSVCRT:  # pragma: no cover - Windows
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        os.close(fd)


class SessionState:
    """Mutable view of one session's state file."""

    def __init__(self, path: Path, data: dict[str, Any]):
        self.path = path
        self.data = data

    # -- lifecycle ---------------------------------------------------------

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def save(self) -> None:
        """Atomically persist state (write to a temp file, then rename)."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(self.data, fh)
        os.replace(tmp, self.path)

    # -- accessors ---------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value stored under ``key``, or ``default`` if absent."""
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key``."""
        self.data[key] = value

    def setdefault(self, key: str, value: Any) -> Any:
        """Store ``value`` under ``key`` only if absent, returning the stored value."""
        return self.data.setdefault(key, value)

    def mark_once(self, key: str) -> bool:
        """Return True the first time ``key`` is claimed, False afterwards.

        Used to emit the workflow and agent records exactly once per session
        even though several processes race to be "first".
        """
        flags = self.data.setdefault("_once", {})
        if flags.get(key):
            return False
        flags[key] = True
        return True

    # -- pending tool calls ------------------------------------------------

    def add_pending(self, key: str, payload: dict[str, Any]) -> None:
        """Record an in-flight tool call under ``key``, pruning stale entries."""
        pending = self.data.setdefault("pending_tools", {})
        payload.setdefault("recorded_at", time.time())
        pending[key] = payload
        self._prune_pending(pending)

    def pop_pending(self, key: str) -> dict[str, Any] | None:
        """Remove and return the pending tool call under ``key``, if any."""
        pending = self.data.setdefault("pending_tools", {})
        value = pending.pop(key, None)
        self._prune_pending(pending)
        return value

    @staticmethod
    def _prune_pending(pending: dict[str, Any]) -> None:
        now = time.time()
        stale = [k for k, v in pending.items() if now - float(v.get("recorded_at", now)) > PENDING_TTL_SECONDS]
        for key in stale:
            pending.pop(key, None)
        if len(pending) > MAX_PENDING:
            ordered = sorted(pending.items(), key=lambda kv: kv[1].get("recorded_at", 0))
            for key, _ in ordered[: len(pending) - MAX_PENDING]:
                pending.pop(key, None)


@contextmanager
def session_state(path: Path) -> Iterator[SessionState]:
    """Open session state for read-modify-write under an exclusive lock."""
    with file_lock(path):
        state = SessionState(path, SessionState._read(path))
        yield state
        state.save()
