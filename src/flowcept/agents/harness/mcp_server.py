"""An MCP server exposing captured provenance as tools.

Two audiences:

*Any MCP client* -- Claude Code, Cursor, an agent of your own -- can ask what
happened in past sessions without knowing the buffer format. That makes
provenance answerable in the same conversation that produced it.

*Harnesses with no hook system* can call ``record_event`` to push provenance in,
which is the only integration path available when a harness can run an MCP
server but cannot run a command per lifecycle event.

Run with ``flowcept-harness-mcp``. Requires the ``mcp`` extra; the capture path
does not.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import Config, load_config

SERVER_NAME = "flowcept-provenance"


def _load_server_class():
    """Return the MCP server class across SDK generations.

    The SDK renamed ``FastMCP`` to ``MCPServer`` in 2.0 while keeping the
    decorator API identical, so supporting both is an import, not a shim.
    """
    try:
        from mcp.server.mcpserver import MCPServer  # SDK >= 2.0

        return MCPServer
    except ImportError:
        pass
    try:
        from mcp.server.fastmcp import FastMCP  # SDK < 2.0

        return FastMCP
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise SystemExit("The MCP server needs the `mcp` package: pip install 'flowcept-harness[mcp]'") from exc


# -- buffer access -----------------------------------------------------------


def _buffers(config: Config) -> list[Path]:
    if not config.buffers_dir.is_dir():
        return []
    return sorted(config.buffers_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def _records(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict):
            out.append(record)
    return out


def _find_buffer(config: Config, session: str | None) -> Path | None:
    buffers = _buffers(config)
    if not buffers:
        return None
    if not session:
        return buffers[0]
    # Accept a full workflow id, a prefix of one, or the harness session id.
    for path in buffers:
        if path.stem == session or path.stem.startswith(session):
            return path
    for path in buffers:
        for record in _records(path):
            if record.get("type") == "workflow" and record.get("used", {}).get("session_id") == session:
                return path
    return None


def _elapsed(record: dict[str, Any]) -> float | None:
    started, ended = record.get("started_at"), record.get("ended_at")
    if isinstance(started, (int, float)) and isinstance(ended, (int, float)):
        return round(ended - started, 3)
    return None


def build_server(config: Config | None = None):
    """Build the MCP server. Separate from :func:`main` so tests can drive it."""
    config = config or load_config()
    server_class = _load_server_class()
    server = server_class(SERVER_NAME)

    @server.tool(
        description=(
            "List captured AI coding sessions, newest first. Returns the workflow id, "
            "harness, status, timing, and per-session totals for turns, tool calls, "
            "tool errors, and subagents."
        )
    )
    def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
        sessions = []
        for path in _buffers(config)[: max(1, limit)]:
            records = _records(path)
            root = next(
                (r for r in records if r.get("type") == "workflow" and r.get("parent_workflow_id") is None),
                None,
            )
            if root is None:
                continue
            sessions.append(
                {
                    "workflow_id": root.get("workflow_id", path.stem),
                    "harness": (root.get("custom_metadata") or {}).get("harness"),
                    "name": root.get("name"),
                    "status": root.get("status"),
                    "started_at": root.get("started_at"),
                    "ended_at": root.get("ended_at"),
                    "elapsed_seconds": _elapsed(root),
                    "cwd": (root.get("used") or {}).get("cwd"),
                    "model": (root.get("used") or {}).get("model"),
                    "totals": root.get("generated") or {},
                }
            )
        return sessions

    @server.tool(
        description=(
            "Get the full activity of one session: every turn, tool call, and subagent "
            "in order. `session` accepts a workflow id or prefix; omit it for the most "
            "recent session."
        )
    )
    def get_session(session: str | None = None, include_io: bool = False) -> dict[str, Any]:
        path = _find_buffer(config, session)
        if path is None:
            return {"error": f"No session matching {session!r}."}

        records = _records(path)
        workflows = {r.get("workflow_id"): r for r in records if r.get("type") == "workflow"}
        activity = []
        for record in records:
            if record.get("type") != "task":
                continue
            wf = workflows.get(record.get("workflow_id")) or {}
            entry = {
                "kind": record.get("subtype"),
                "name": record.get("activity_id"),
                "status": record.get("status"),
                "elapsed_seconds": _elapsed(record),
                "in_subagent": wf.get("name") if wf.get("parent_workflow_id") else None,
                "error": record.get("stderr"),
            }
            if include_io:
                entry["used"] = record.get("used")
                entry["generated"] = record.get("generated")
            activity.append({k: v for k, v in entry.items() if v is not None})

        root = next((w for w in workflows.values() if not w.get("parent_workflow_id")), {})
        return {
            "workflow_id": root.get("workflow_id", path.stem),
            "status": root.get("status"),
            "totals": root.get("generated") or {},
            "subagents": [
                {"name": w.get("name"), "status": w.get("status"), "elapsed_seconds": _elapsed(w)}
                for w in workflows.values()
                if w.get("parent_workflow_id")
            ],
            "activity": activity,
        }

    @server.tool(
        description=(
            "Search tool calls across captured sessions. Filter by tool name, status "
            "('ERROR' finds failures), or a substring of the tool's inputs. Useful for "
            "'what commands have I run', 'what has been failing', 'when did I last touch X'."
        )
    )
    def search_tool_calls(
        tool_name: str | None = None,
        status: str | None = None,
        contains: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        hits: list[dict[str, Any]] = []
        for path in _buffers(config):
            for record in _records(path):
                if record.get("subtype") != "agent_tool":
                    continue
                if tool_name and record.get("activity_id") != tool_name:
                    continue
                if status and record.get("status") != status.upper():
                    continue
                if contains and contains.lower() not in json.dumps(record.get("used") or {}).lower():
                    continue
                hits.append(
                    {
                        "session": path.stem[:8],
                        "tool": record.get("activity_id"),
                        "status": record.get("status"),
                        "elapsed_seconds": _elapsed(record),
                        "used": record.get("used"),
                        "error": record.get("stderr"),
                        "at": record.get("started_at"),
                    }
                )
                if len(hits) >= limit:
                    return hits
        return hits

    @server.tool(
        description=(
            "Aggregate statistics over captured sessions: tool call counts and failure "
            "rates by tool, total time per tool, and the slowest individual calls."
        )
    )
    def session_stats(session: str | None = None) -> dict[str, Any]:
        paths = [p for p in ([_find_buffer(config, session)] if session else _buffers(config)) if p]
        by_tool: dict[str, dict[str, Any]] = {}
        slowest: list[dict[str, Any]] = []

        for path in paths:
            for record in _records(path):
                if record.get("subtype") != "agent_tool":
                    continue
                name = record.get("activity_id", "?")
                stats = by_tool.setdefault(name, {"calls": 0, "errors": 0, "seconds": 0.0})
                stats["calls"] += 1
                if record.get("status") == "ERROR":
                    stats["errors"] += 1
                elapsed = _elapsed(record)
                if elapsed is not None:
                    stats["seconds"] = round(stats["seconds"] + elapsed, 3)
                    slowest.append({"tool": name, "seconds": elapsed, "session": path.stem[:8]})

        slowest.sort(key=lambda r: r["seconds"], reverse=True)
        return {
            "sessions": len(paths),
            "by_tool": dict(sorted(by_tool.items(), key=lambda kv: kv[1]["calls"], reverse=True)),
            "slowest_calls": slowest[:10],
        }

    # -- provenance analysis tools (thin wrappers over prov_analysis.core) ----

    def _session_records(session: str | None):
        path = _find_buffer(config, session)
        if path is None:
            return None, {"error": f"No session matching {session!r}."}
        return _records(path), None

    @server.tool(
        description=(
            "Analyze one captured session end to end: execution summary (counts by "
            "activity/subtype, statuses, duration bounds, token usage) plus per-agent "
            "behavior (turns, tool calls by tool, LLM calls, subagents). `session` "
            "accepts a workflow id or prefix; omit it for the most recent session."
        )
    )
    def analyze_session(session: str | None = None) -> dict[str, Any]:
        from flowcept.agents.prov_analysis import core as prov_core

        records, error = _session_records(session)
        if error:
            return error
        return {
            "summary": prov_core.summarize_execution(records),
            "agent_behavior": prov_core.analyze_agent_behavior(records),
        }

    @server.tool(
        description=(
            "Analyze failures in one captured session: failed tasks grouped by "
            "activity with error excerpts, error rate per activity, and first/last "
            "failure times. Omit `session` for the most recent session."
        )
    )
    def analyze_errors(session: str | None = None) -> dict[str, Any]:
        from flowcept.agents.prov_analysis import core as prov_core

        records, error = _session_records(session)
        if error:
            return error
        return prov_core.analyze_errors(records)

    @server.tool(
        description=(
            "Find the slowest tasks of one captured session, longest elapsed first, "
            "with activity, status, and parent-chain depth. Omit `session` for the "
            "most recent session."
        )
    )
    def find_slowest(session: str | None = None, limit: int = 10) -> list[dict[str, Any]]:
        from flowcept.agents.prov_analysis import core as prov_core

        records, error = _session_records(session)
        if error:
            return [error]
        return prov_core.find_slowest_tasks(records, limit=limit)

    @server.tool(
        description=(
            "List cross-framework provenance links in one captured session: edges "
            "built from source_agent_id pointers between frameworks (e.g. a LangGraph "
            "run linked to a task from another agent framework), plus the count of "
            "unlinked tasks. Omit `session` for the most recent session."
        )
    )
    def cross_links(session: str | None = None) -> dict[str, Any]:
        from flowcept.agents.prov_analysis import core as prov_core

        records, error = _session_records(session)
        if error:
            return error
        return prov_core.cross_framework_links(records)

    @server.tool(
        description=(
            "Record a provenance event from a harness that has no hook system. `kind` is "
            "one of session_start, prompt, tool_pre, tool_post, tool_error, llm_call, "
            "turn_end, subagent_start, subagent_stop, session_end. Pass the same "
            "`session_id` and `harness` for every event in one session: together they "
            "identify the session, so changing either starts a separate one."
        )
    )
    def record_event(
        kind: str,
        session_id: str,
        harness: str = "mcp",
        tool_name: str | None = None,
        tool_input: dict[str, Any] | None = None,
        tool_response: dict[str, Any] | None = None,
        prompt: str | None = None,
        response: str | None = None,
        model: str | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        from .events import HarnessEvent
        from .recorder import Recorder
        from .vocab import EventKind

        if kind not in EventKind.ALL:
            return {"error": f"Unknown kind {kind!r}. Valid kinds: {sorted(EventKind.ALL)}"}

        records = Recorder(config).record(
            HarnessEvent(
                kind=kind,
                harness=harness,
                session_id=session_id,
                timestamp=time.time(),
                model=model,
                prompt=prompt,
                response=response,
                tool_name=tool_name,
                tool_input=tool_input,
                tool_response=tool_response,
                error=error,
            )
        )
        return {"recorded": len(records)}

    @server.tool(
        description=(
            "Generate a Flowcept workflow card for a session: a markdown report with "
            "timings, status counts, slowest activities, and per-workflow detail."
        )
    )
    def generate_report(session: str | None = None) -> dict[str, Any]:
        path = _find_buffer(config, session)
        if path is None:
            return {"error": f"No session matching {session!r}."}
        try:
            from flowcept import Flowcept
        except ImportError:
            return {"error": "flowcept is not installed; pip install 'flowcept-harness[ingest]'"}

        stats = Flowcept.generate_report(
            report_type="workflow_card",
            input_jsonl_path=str(path),
            format="markdown",
        )
        return {"markdown": stats.get("markdown"), "workflows": stats.get("n_workflows"), "tasks": stats.get("n_tasks")}

    return server


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``flowcept-harness-mcp``."""
    import argparse

    parser = argparse.ArgumentParser(prog="flowcept-harness-mcp", description=__doc__)
    parser.add_argument("--transport", default="stdio", choices=("stdio", "sse", "streamable-http"))
    args = parser.parse_args(argv)

    build_server().run(transport=args.transport)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
