"""Write provenance records.

The default (and always-on) sink is a per-session JSONL file whose records are
byte-for-byte the dicts Flowcept itself buffers — ``{"type": "workflow"|"task"|
"agent", ...}``. That means the buffer is directly consumable by
``flowcept --generate-report --input-path <file>`` and by
``flowcept.agents.harness flush`` with no conversion step.

An optional online sink publishes the same dicts to the Flowcept message queue.
It is off by default because it would add a Redis round-trip to every keystroke-
adjacent hook.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .config import Config
from .state import file_lock

_HOSTNAME: str | None = None
_SYSTEM: str | None = None
_LOGIN: str | None = None


def hostname() -> str:
    """Return this machine's name.

    ``os.uname`` is preferred over ``socket.gethostname`` purely for import
    cost: ``socket`` is ~11ms to import and this is the only thing it was
    needed for. Same for ``getpass`` and ``platform`` below.
    """
    global _HOSTNAME
    if _HOSTNAME is None:
        try:
            _HOSTNAME = os.uname().nodename
        except AttributeError:  # Windows
            import socket

            try:
                _HOSTNAME = socket.gethostname()
            except OSError:
                _HOSTNAME = "unknown"
    return _HOSTNAME or "unknown"


def system_name() -> str:
    """Return the OS name, as ``platform.system()`` would spell it."""
    global _SYSTEM
    if _SYSTEM is None:
        try:
            _SYSTEM = os.uname().sysname
        except AttributeError:  # Windows
            _SYSTEM = "Windows"
    return _SYSTEM


def login_name() -> str:
    """Return the current user's login name, cached after the first lookup."""
    global _LOGIN
    if _LOGIN is None:
        _LOGIN = os.environ.get("USER") or os.environ.get("USERNAME") or ""
        if not _LOGIN:
            import getpass

            try:
                _LOGIN = getpass.getuser()
            except Exception:
                _LOGIN = "unknown"
    return _LOGIN


def _default(obj: Any) -> str:
    return repr(obj)


class JsonlEmitter:
    """JSONL sink, safe against concurrent hook processes.

    Appends, except when a record supersedes an earlier one for the same
    workflow (see :meth:`write`).
    """

    def __init__(self, path: Path):
        self.path = path

    def write(self, records: Iterable[dict[str, Any]], supersede: frozenset[str] | None = None) -> int:
        """Write ``records``, dropping superseded workflow records first.

        A workflow is written twice: once when it opens, so an in-flight or
        crashed session is still readable, and once when it closes with its
        final status and totals. Only the second one should survive. Flowcept's
        loader keeps the last workflow record per file, but *only* when the file
        holds a single workflow -- with subagents it holds several, and every
        record is then counted as a distinct run. So on close the prior record
        for that ``workflow_id`` is dropped in a single rewrite rather than
        left to be deduplicated downstream.
        """
        records = [r for r in records if r]
        if not records:
            return 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(r, default=_default, ensure_ascii=False) + "\n" for r in records)
        # A single locked append keeps records from interleaving mid-line when
        # parallel tool calls flush at the same moment.
        with file_lock(self.path):
            if supersede and self.path.exists():
                self._rewrite_without(supersede, payload)
            else:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(payload)
        return len(records)

    def _rewrite_without(self, workflow_ids: frozenset[str], payload: str) -> None:
        """Rewrite the buffer without workflow records for ``workflow_ids``.

        Caller must hold the lock. One streaming pass into a temp file, then an
        atomic replace, so a reader never sees a partial buffer. Cost is one
        file rewrite per session or subagent close, not per event.
        """
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        dropped = False
        with self.path.open("r", encoding="utf-8") as src, tmp.open("w", encoding="utf-8") as dst:
            for line in src:
                stripped = line.strip()
                if stripped:
                    try:
                        record = json.loads(stripped)
                    except ValueError:
                        record = None
                    if (
                        isinstance(record, dict)
                        and record.get("type") == "workflow"
                        and record.get("workflow_id") in workflow_ids
                    ):
                        dropped = True
                        continue
                dst.write(line)
            dst.write(payload)
        if dropped:
            os.replace(str(tmp), str(self.path))
        else:
            # Nothing to drop: the rewrite was wasted work, so keep the cheaper
            # append and leave the original file untouched.
            tmp.unlink(missing_ok=True)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(payload)


class OnlinePublisher:
    """Publishes records to the Flowcept MQ. Import of flowcept is deferred."""

    def __init__(self) -> None:
        self._mq = None

    def write(self, records: Iterable[dict[str, Any]]) -> int:
        """Publish ``records`` to the MQ, building the connection on first use."""
        records = [r for r in records if r]
        if not records:
            return 0
        if self._mq is None:
            from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao

            self._mq = MQDao.build()
        self._mq.bulk_publish(records)
        return len(records)


class Emitter:
    """Fan-out to the configured sinks. Never raises into the harness."""

    def __init__(self, config: Config, workflow_id: str, on_error=None):
        self.config = config
        self.jsonl = JsonlEmitter(config.buffer_path(workflow_id))
        self.online = OnlinePublisher() if config.online else None
        self._on_error = on_error

    def emit(self, *records: dict[str, Any], supersede: frozenset[str] | None = None) -> int:
        """Write ``records`` to every configured sink, swallowing sink errors."""
        flat = [r for r in records if r]
        if not flat:
            return 0
        written = 0
        try:
            written = self.jsonl.write(flat, supersede=supersede)
        except Exception as exc:  # capture must never break the harness
            if self._on_error:
                self._on_error(f"jsonl write failed: {exc!r}")
        if self.online is not None:
            try:
                self.online.write(flat)
            except Exception as exc:
                if self._on_error:
                    self._on_error(f"online publish failed: {exc!r}")
        return written
