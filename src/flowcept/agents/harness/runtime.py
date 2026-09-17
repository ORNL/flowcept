"""Guard rails for code that runs on a harness's critical path.

A capture hook has one hard obligation: never make the harness worse. It must
not block the UI, must not write to stdout (some events feed stdout straight
into the model's context), and must not fail in a way the harness reports as an
error. Everything here exists to enforce that.
"""

from __future__ import annotations

import os
import signal
import sys
import threading
import time
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import Config, load_config


def log_error(config: Config, message: str) -> None:
    """Append a capture failure to the harness log. Never raises."""
    try:
        config.home.mkdir(parents=True, exist_ok=True)
        with config.log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} pid={os.getpid()} {message}\n")
    except Exception:
        pass


class _Watchdog:
    """Hard-exit the process if capture overruns its budget.

    A hook that hangs (a stuck lock, a wedged network sink) stalls the harness.
    Losing one provenance record is strictly better than that, so past the
    deadline we abandon the work and exit cleanly.
    """

    def __init__(self, timeout_ms: int):
        self.timeout = max(timeout_ms, 100) / 1000.0
        self._timer: threading.Timer | None = None

    def __enter__(self):
        if self.timeout <= 0:
            return self
        self._timer = threading.Timer(self.timeout, self._fire)
        self._timer.daemon = True
        self._timer.start()
        return self

    def __exit__(self, *exc):
        if self._timer:
            self._timer.cancel()
        return False

    @staticmethod
    def _fire():
        # os._exit skips atexit/flush handlers on purpose: we are already past
        # the point where an orderly shutdown is affordable.
        os._exit(0)


def run_capture(fn: Callable[[Config], Any], config: Config | None = None) -> int:
    """Run ``fn`` under the capture safety contract; always return 0."""
    try:
        config = config or load_config()
    except Exception:
        return 0

    if not config.enabled:
        return 0

    try:
        with _Watchdog(config.timeout_ms):
            fn(config)
    except Exception:
        log_error(config, "capture failed:\n" + traceback.format_exc())
        if config.debug:
            # Stderr on exit 0 goes to the harness debug log only, never to the
            # model, so this is safe to surface when explicitly debugging.
            print(traceback.format_exc(), file=sys.stderr)
    return 0


def read_stdin_json() -> dict[str, Any]:
    """Read a JSON object from stdin; return ``{}`` on anything unexpected."""
    import json

    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    raw = (raw or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def detach() -> bool:
    """Fork a child to finish the work and return control to the harness now.

    Only used when the sink may be slow (online publishing). Returns True in
    the parent (which should return immediately) and False in the child.
    """
    if not hasattr(os, "fork"):
        return False
    try:
        pid = os.fork()
    except OSError:
        return False
    if pid > 0:
        return True
    # Child: detach from the harness's process group so it is not killed with it.
    try:
        os.setsid()
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        devnull = os.open(os.devnull, os.O_RDWR)
        os.dup2(devnull, 0)
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
    except Exception:
        pass
    return False


def project_dir_from_env(fallback: str | None = None) -> str | None:
    """Best-effort project root, preferring what the harness told us."""
    for var in ("CLAUDE_PROJECT_DIR", "FLOWCEPT_HARNESS_PROJECT_DIR"):
        value = os.environ.get(var)
        if value:
            return value
    if fallback:
        return fallback
    try:
        return str(Path.cwd())
    except OSError:
        return None
