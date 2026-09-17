#!/usr/bin/env bash
# Optional auto-report on SessionEnd. Off by default: does nothing unless
# FLOWCEPT_HARNESS_AUTOREPORT=1. When enabled, generates a Flowcept workflow
# card for the session that just ended and writes it to
# $FLOWCEPT_HARNESS_HOME/reports/<workflow_id>.md.
#
# Same discipline as hook.sh:
#
#   1. Never fail. Every path ends in `exit 0`.
#   2. Never write to stdout. Hook stdout can be injected into model context.
#   3. Never block the user. This runs on SessionEnd only, after the session
#      is over, so a report is allowed to take seconds -- but still capped by
#      the hook timeout in hooks.json.

set -u

# Off by default: consume stdin (some CLIs treat an unread pipe as an error)
# and leave silently.
if [ "${FLOWCEPT_HARNESS_AUTOREPORT:-0}" != "1" ]; then
  cat >/dev/null 2>&1 || true
  exit 0
fi

# --- locate an interpreter (same resolution as hook.sh) ----------------------
PY="${FLOWCEPT_HARNESS_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
fi
[ -z "$PY" ] && exit 0

# --- locate the package (same resolution as hook.sh) -------------------------
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
for path in "$ROOT/vendor" "$ROOT/../../src"; do
  if [ -d "$path/flowcept" ]; then
    PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$path"
    export PYTHONPATH
    break
  fi
done

# Map the SessionEnd payload's session_id to its buffer, then run the report
# through `flowcept-harness report --input <buffer> -o <reports/<id>.md>`.
# Falls back to the most recent buffer when the payload is unusable. stdout to
# /dev/null enforces rule 2; failures land in the log, never on the user.
"$PY" - <<'PYEOF' >/dev/null 2>>"${FLOWCEPT_HARNESS_LOG:-/dev/null}" || true
import json
import os
import pathlib
import sys

home = pathlib.Path(
    os.environ.get("FLOWCEPT_HARNESS_HOME", pathlib.Path.home() / ".flowcept" / "harness")
).expanduser()

try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}
session_id = payload.get("session_id") if isinstance(payload, dict) else None

buffers = sorted(home.glob("buffers/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
buf = None
if session_id:
    for path in buffers:
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("type") == "workflow" and (record.get("used") or {}).get("session_id") == session_id:
                    buf = path
                    break
        except Exception:
            continue
        if buf is not None:
            break
if buf is None and buffers:
    buf = buffers[0]
if buf is None:
    raise SystemExit(0)

reports = home / "reports"
reports.mkdir(parents=True, exist_ok=True)
out = reports / (buf.stem + ".md")

from flowcept.agents.harness.cli import main

raise SystemExit(main(["report", "--input", str(buf), "-o", str(out)]))
PYEOF
exit 0
