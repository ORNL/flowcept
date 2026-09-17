#!/usr/bin/env bash
# Launch the flowcept-provenance MCP server over stdio.
#
# Interpreter and package resolution mirror hook.sh: FLOWCEPT_HARNESS_PYTHON
# wins, then python3/python on PATH; an installed flowcept wins, then the repo
# checkout this plugin ships in. Unlike hook.sh, stdout is NOT suppressed --
# stdout *is* the MCP stdio transport. Diagnostics go to stderr, which the MCP
# client logs.
#
# The module runs as __main__ (it has an `if __name__ == "__main__"` guard), so
# `python -m flowcept.agents.harness.mcp_server` is equivalent to the console
# script `flowcept-harness-mcp`; the module form works without an entry-point
# install. It needs the `mcp` package: pip install 'flowcept[dev]' or `mcp`.

set -u

PY="${FLOWCEPT_HARNESS_PYTHON:-}"
if [ -z "$PY" ]; then
  for candidate in python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY="$candidate"
      break
    fi
  done
fi
if [ -z "$PY" ]; then
  echo "flowcept-provenance: no python interpreter found" >&2
  exit 1
fi

ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
for path in "$ROOT/vendor" "$ROOT/../../src"; do
  if [ -d "$path/flowcept" ]; then
    PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$path"
    export PYTHONPATH
    break
  fi
done

exec "$PY" -m flowcept.agents.harness.mcp_server --transport stdio
