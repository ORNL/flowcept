#!/usr/bin/env bash
# Provenance hook shim. Reads a Claude Code hook payload on stdin and records
# it. Argument 1 is the hook event name, used as a fallback on CLI versions
# that omit `hook_event_name` from the payload.
#
# Three rules this script exists to enforce:
#
#   1. Never fail. A non-zero exit from a hook is surfaced to the user, and on
#      some events a hook can block the turn outright. Capture is not worth
#      interrupting anyone's work, so every path ends in `exit 0`.
#   2. Never write to stdout. On UserPromptSubmit and SessionStart, a hook's
#      stdout is injected into the model's context.
#   3. Never be slow. The capture path is stdlib-only precisely so this can be
#      a bare interpreter start with no third-party imports.

set -u

# --- locate an interpreter --------------------------------------------------
# FLOWCEPT_HARNESS_PYTHON wins, for pyenv/conda setups where `python3` on PATH
# is not the one with flowcept-harness installed.
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

# --- locate the package -----------------------------------------------------
# Prefer an installed flowcept; fall back to the repo checkout the plugin
# ships in, so the plugin works with nothing pip-installed at all.
ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
for path in "$ROOT/vendor" "$ROOT/../../src"; do
  if [ -d "$path/flowcept" ]; then
    PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$path"
    export PYTHONPATH
    break
  fi
done

# stdout to /dev/null enforces rule 2 even if something downstream prints.
"$PY" -m flowcept.agents.claude_code.claude_code_plugin --event "${1:-}" \
  >/dev/null 2>>"${FLOWCEPT_HARNESS_LOG:-/dev/null}" || true
exit 0
