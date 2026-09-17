"""Pure analysis functions over PROV-AGENT provenance records.

Every function here takes ``records: list[dict]`` — a mixed list of workflow,
task, and agent records as produced either by the harness buffer
(``flowcept.agents.harness``) or by the framework plugins (LangGraph, CrewAI,
AutoGen, Academy).  Records are inspected per record via their ``type`` /
``subtype`` fields, and any field that may be absent degrades gracefully.

This module is dependency-light on purpose: stdlib plus
:mod:`flowcept.report.aggregations` (itself stdlib-only), so the harness MCP
server can import it lazily without pulling pandas or any backend.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional

from flowcept.report.aggregations import (
    as_float,
    elapsed_seconds,
    fmt_timestamp_utc,
    group_activities,
    workflow_bounds,
)

__all__ = [
    "load_records",
    "summarize_execution",
    "analyze_errors",
    "analyze_agent_behavior",
    "find_slowest_tasks",
    "cross_framework_links",
    "compare_executions",
]

_STATUS_ERROR = "ERROR"

#: Token-usage keys observed in real records (harness ``custom_metadata.llm_usage``
#: and framework-plugin ``generated`` fields).
_USAGE_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
)


# -- record classification -----------------------------------------------------


def _is_workflow(record: Dict[str, Any]) -> bool:
    return record.get("type") == "workflow"


def _is_agent(record: Dict[str, Any]) -> bool:
    return record.get("type") == "agent"


def _is_task(record: Dict[str, Any]) -> bool:
    # Harness records always carry ``type: task``; framework-plugin task dicts
    # may omit ``type`` but always carry a ``task_id``.
    if record.get("type") == "task":
        return True
    return record.get("type") is None and record.get("task_id") is not None


def _tasks(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in records if _is_task(r)]


def _workflows(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [r for r in records if _is_workflow(r)]


def _filter_workflow(records: List[Dict[str, Any]], workflow_id: Optional[str]) -> List[Dict[str, Any]]:
    if not workflow_id:
        return records
    return [r for r in records if r.get("workflow_id") == workflow_id]


def _custom_metadata(record: Dict[str, Any]) -> Dict[str, Any]:
    meta = record.get("custom_metadata")
    return meta if isinstance(meta, dict) else {}


def _task_usage(record: Dict[str, Any]) -> Dict[str, float]:
    """Extract token-usage numbers from one task record.

    Looks in ``custom_metadata.llm_usage`` (harness shape) and in ``generated``
    (framework-plugin shape, e.g. ``generated.total_tokens``).
    """
    usage: Dict[str, float] = {}
    sources: List[Dict[str, Any]] = []
    llm_usage = _custom_metadata(record).get("llm_usage")
    if isinstance(llm_usage, dict):
        sources.append(llm_usage)
    generated = record.get("generated")
    if isinstance(generated, dict):
        sources.append(generated)
    for source in sources:
        for key in _USAGE_KEYS:
            val = as_float(source.get(key))
            if val is not None:
                usage[key] = usage.get(key, 0.0) + val
    return usage


def _sum_usage(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    totals: Dict[str, float] = {}
    tasks_with_usage = 0
    for task in tasks:
        usage = _task_usage(task)
        if not usage:
            continue
        tasks_with_usage += 1
        for key, val in usage.items():
            totals[key] = totals.get(key, 0.0) + val
    return {"totals": {k: int(v) for k, v in totals.items()}, "n_tasks_with_usage": tasks_with_usage}


def _framework_of(record: Dict[str, Any]) -> Optional[str]:
    """Best-effort name of the framework/harness a record came from."""
    harness = _custom_metadata(record).get("harness")
    if harness:
        return str(harness)
    adapter = record.get("adapter_id")
    if adapter:
        return str(adapter).rsplit(".", 1)[-1]
    subtype = record.get("subtype")
    if isinstance(subtype, str) and "_" in subtype and subtype.split("_", 1)[0] in ("langgraph", "crewai", "autogen"):
        return subtype.split("_", 1)[0]
    return None


# -- loading -------------------------------------------------------------------


def load_records(
    jsonl_path: Optional[str] = None,
    records: Optional[List[Dict[str, Any]]] = None,
    workflow_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Load provenance records from a JSONL buffer, a list, or the Flowcept DB.

    Parameters
    ----------
    jsonl_path : str, optional
        Path to a JSONL buffer file (harness buffer or dumped Flowcept buffer).
    records : list of dict, optional
        Already-loaded records; returned as-is (list-copied).
    workflow_id : str, optional
        When neither ``jsonl_path`` nor ``records`` is given, load this
        workflow from the Flowcept DB (requires a reachable backend).
    campaign_id : str, optional
        Same as ``workflow_id`` but for a whole campaign.

    Returns
    -------
    list of dict
        Mixed workflow/task/agent records.
    """
    if records is not None:
        return list(records)
    if jsonl_path is not None:
        from pathlib import Path

        from flowcept.report.loaders import read_jsonl

        loaded, _skipped = read_jsonl(Path(jsonl_path))
        return loaded
    if workflow_id or campaign_id:
        # Guarded, lazy DB loading: only reached when explicitly requested.
        from flowcept.report.loaders import load_records_from_db

        dataset = load_records_from_db(workflow_id=workflow_id, campaign_id=campaign_id)
        out: List[Dict[str, Any]] = []
        for wf in dataset.get("workflows") or ([dataset["workflow"]] if dataset.get("workflow") else []):
            wf = dict(wf)
            wf.setdefault("type", "workflow")
            out.append(wf)
        for task in dataset.get("tasks") or []:
            task = dict(task)
            task.setdefault("type", "task")
            out.append(task)
        return out
    return []


# -- analyses ------------------------------------------------------------------


def summarize_execution(records: List[Dict[str, Any]], workflow_id: Optional[str] = None) -> Dict[str, Any]:
    """Summarize an execution: counts, duration bounds, statuses, agents, token usage.

    Parameters
    ----------
    records : list of dict
        Mixed workflow/task records (harness or framework-plugin shape).
    workflow_id : str, optional
        Restrict the summary to records of one workflow.

    Returns
    -------
    dict
        Counts by type/subtype/activity, duration bounds, status counts,
        campaigns and agents seen, and token-usage totals where present.
    """
    records = _filter_workflow(records, workflow_id)
    tasks = _tasks(records)
    workflows = _workflows(records)

    by_type = Counter(str(r.get("type") or ("task" if _is_task(r) else "unknown")) for r in records)
    by_subtype = Counter(str(t.get("subtype", "unknown")) for t in tasks)
    by_activity = Counter(str(t.get("activity_id", "unknown")) for t in tasks)
    status_counts = Counter(str(t.get("status", "unknown")) for t in tasks)

    min_start, max_end, total_elapsed = workflow_bounds(tasks)
    if total_elapsed is None and workflows:
        min_start, max_end, total_elapsed = workflow_bounds(workflows)

    campaigns = sorted({str(r["campaign_id"]) for r in records if r.get("campaign_id")})
    agent_ids = {str(r["agent_id"]) for r in records if r.get("agent_id")}
    agent_names = sorted({str(r["name"]) for r in records if _is_agent(r) and r.get("name")})

    return {
        "n_records": len(records),
        "n_workflows": len(workflows),
        "n_tasks": len(tasks),
        "counts_by_type": dict(by_type),
        "tasks_by_subtype": dict(by_subtype),
        "tasks_by_activity": dict(by_activity),
        "status_counts": dict(status_counts),
        "started_at": min_start,
        "ended_at": max_end,
        "started_at_utc": fmt_timestamp_utc(min_start) if min_start is not None else None,
        "ended_at_utc": fmt_timestamp_utc(max_end) if max_end is not None else None,
        "total_elapsed_seconds": total_elapsed,
        "campaigns": campaigns,
        "agents": sorted(agent_ids),
        "agent_names": agent_names,
        "token_usage": _sum_usage(tasks),
        "activities": group_activities(tasks) if tasks else [],
    }


def analyze_errors(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Analyze failed tasks: per-activity failures, error rates, first/last failure.

    Parameters
    ----------
    records : list of dict
        Mixed provenance records.

    Returns
    -------
    dict
        ``by_activity`` maps activity_id to failure count, error rate, and
        stderr/message excerpts; plus overall counts and failure time bounds.
    """
    tasks = _tasks(records)
    failed = [t for t in tasks if str(t.get("status")) == _STATUS_ERROR]

    totals_by_activity = Counter(str(t.get("activity_id", "unknown")) for t in tasks)
    by_activity: Dict[str, Dict[str, Any]] = {}
    for task in failed:
        activity = str(task.get("activity_id", "unknown"))
        entry = by_activity.setdefault(activity, {"n_failed": 0, "error_rate": 0.0, "excerpts": []})
        entry["n_failed"] += 1
        message = task.get("stderr") or _custom_metadata(task).get("error") or task.get("stdout")
        if message and len(entry["excerpts"]) < 5:
            entry["excerpts"].append(str(message)[:300])
    for activity, entry in by_activity.items():
        total = totals_by_activity.get(activity, 0)
        entry["n_total"] = total
        entry["error_rate"] = round(entry["n_failed"] / total, 4) if total else None

    failure_starts = [as_float(t.get("started_at")) for t in failed]
    failure_starts = [s for s in failure_starts if s is not None]
    first = min(failure_starts) if failure_starts else None
    last = max(failure_starts) if failure_starts else None

    return {
        "n_tasks": len(tasks),
        "n_failed": len(failed),
        "overall_error_rate": round(len(failed) / len(tasks), 4) if tasks else None,
        "by_activity": by_activity,
        "first_failure_at": first,
        "last_failure_at": last,
        "first_failure_at_utc": fmt_timestamp_utc(first) if first is not None else None,
        "last_failure_at_utc": fmt_timestamp_utc(last) if last is not None else None,
    }


def analyze_agent_behavior(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Profile agent behavior per agent/session.

    For each agent (falling back to the session workflow when no ``agent_id``
    is present): turns, tool calls by tool, LLM calls, token usage, and
    avg/max task durations.  Session workflows and subagent counts are
    reported alongside.

    Parameters
    ----------
    records : list of dict
        Mixed provenance records.

    Returns
    -------
    dict
        ``agents`` keyed by agent/session id, plus ``sessions`` and
        ``n_subagent_sessions``.
    """
    tasks = _tasks(records)
    workflows = _workflows(records)

    agents: Dict[str, Dict[str, Any]] = {}
    durations: Dict[str, List[float]] = defaultdict(list)
    for task in tasks:
        key = str(task.get("agent_id") or task.get("workflow_id") or "unknown")
        entry = agents.setdefault(
            key,
            {
                "turns": 0,
                "llm_calls": 0,
                "tool_calls": 0,
                "tool_calls_by_tool": {},
                "token_usage": {},
                "n_tasks": 0,
                "n_errors": 0,
            },
        )
        entry["n_tasks"] += 1
        if str(task.get("status")) == _STATUS_ERROR:
            entry["n_errors"] += 1
        subtype = str(task.get("subtype", ""))
        granularity = _custom_metadata(task).get("granularity")
        if subtype == "ai_model_invocation":
            if granularity == "call":
                entry["llm_calls"] += 1
            else:
                entry["turns"] += 1
        elif subtype == "llm_call":
            entry["llm_calls"] += 1
        elif subtype in ("agent_tool", "tool_call"):
            entry["tool_calls"] += 1
            tool = str(task.get("activity_id", "unknown"))
            entry["tool_calls_by_tool"][tool] = entry["tool_calls_by_tool"].get(tool, 0) + 1
        for usage_key, val in _task_usage(task).items():
            entry["token_usage"][usage_key] = int(entry["token_usage"].get(usage_key, 0) + val)
        elapsed = elapsed_seconds(task.get("started_at"), task.get("ended_at"))
        if elapsed is not None:
            durations[key].append(elapsed)

    for key, entry in agents.items():
        vals = durations.get(key) or []
        entry["avg_task_seconds"] = round(sum(vals) / len(vals), 4) if vals else None
        entry["max_task_seconds"] = round(max(vals), 4) if vals else None

    subagent_workflows = [w for w in workflows if w.get("parent_workflow_id")]
    subagents_by_parent = Counter(str(w.get("parent_workflow_id")) for w in subagent_workflows)
    sessions = []
    for wf in workflows:
        if wf.get("parent_workflow_id"):
            continue
        wid = str(wf.get("workflow_id", "unknown"))
        sessions.append(
            {
                "workflow_id": wid,
                "name": wf.get("name"),
                "subtype": wf.get("subtype"),
                "status": wf.get("status"),
                "elapsed_seconds": elapsed_seconds(wf.get("started_at"), wf.get("ended_at")),
                "n_subagents": subagents_by_parent.get(wid, 0),
            }
        )

    return {
        "agents": agents,
        "sessions": sessions,
        "n_subagent_sessions": len(subagent_workflows),
    }


def find_slowest_tasks(records: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """Return the slowest tasks, longest elapsed first.

    Parameters
    ----------
    records : list of dict
        Mixed provenance records.
    limit : int, optional
        Maximum number of rows returned (default 10).

    Returns
    -------
    list of dict
        Rows with ``task_id``, ``activity_id``, ``subtype``, ``elapsed_seconds``,
        ``status``, and ``parent_depth`` (length of the parent_task_id chain).
    """
    tasks = _tasks(records)
    by_id = {t.get("task_id"): t for t in tasks if t.get("task_id")}

    def depth(task: Dict[str, Any]) -> int:
        seen = set()
        d = 0
        current = task
        while True:
            parent_id = current.get("parent_task_id")
            if not parent_id or parent_id in seen:
                return d
            seen.add(parent_id)
            d += 1
            parent = by_id.get(parent_id)
            if parent is None:
                return d
            current = parent

    rows = []
    for task in tasks:
        elapsed = elapsed_seconds(task.get("started_at"), task.get("ended_at"))
        if elapsed is None:
            continue
        rows.append(
            {
                "task_id": task.get("task_id"),
                "activity_id": task.get("activity_id"),
                "subtype": task.get("subtype"),
                "elapsed_seconds": round(elapsed, 4),
                "status": task.get("status"),
                "parent_depth": depth(task),
            }
        )
    rows.sort(key=lambda r: r["elapsed_seconds"], reverse=True)
    return rows[: max(0, int(limit))]


def cross_framework_links(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Extract cross-framework provenance links between records.

    A link exists when a task carries a source pointer — top-level
    ``source_agent_id``, ``custom_metadata.source_agent_id``, or the raw
    ``_source_agent_id`` key inside ``used`` / ``used.inputs`` — naming a task
    or agent from another framework.

    Parameters
    ----------
    records : list of dict
        Mixed provenance records.

    Returns
    -------
    dict
        ``links`` (list of ``{source_task_id, target_task_id,
        target_workflow_id, frameworks}``), ``n_links``, ``n_unlinked_tasks``,
        and ``frameworks_seen``.
    """
    tasks = _tasks(records)
    by_id: Dict[str, Dict[str, Any]] = {}
    for record in records:
        for id_key in ("task_id", "agent_id", "workflow_id"):
            rid = record.get(id_key)
            if rid and rid not in by_id:
                by_id[str(rid)] = record

    links = []
    linked_task_ids = set()
    for task in tasks:
        used = task.get("used") if isinstance(task.get("used"), dict) else {}
        inputs = used.get("inputs") if isinstance(used.get("inputs"), dict) else {}
        source = (
            task.get("source_agent_id")
            or _custom_metadata(task).get("source_agent_id")
            or used.get("_source_agent_id")
            or inputs.get("_source_agent_id")
        )
        if not source:
            continue
        source = str(source)
        source_record = by_id.get(source)
        frameworks = [fw for fw in (_framework_of(source_record) if source_record else None, _framework_of(task)) if fw]
        links.append(
            {
                "source_task_id": source,
                "target_task_id": task.get("task_id"),
                "target_workflow_id": task.get("workflow_id"),
                "frameworks": frameworks,
            }
        )
        linked_task_ids.add(task.get("task_id"))

    frameworks_seen = sorted({fw for r in records if (fw := _framework_of(r))})
    return {
        "links": links,
        "n_links": len(links),
        "n_unlinked_tasks": len([t for t in tasks if t.get("task_id") not in linked_task_ids]),
        "frameworks_seen": frameworks_seen,
    }


def compare_executions(records_a: List[Dict[str, Any]], records_b: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compare two executions per activity: count, duration, and error-rate deltas.

    Parameters
    ----------
    records_a : list of dict
        Records of the first execution.
    records_b : list of dict
        Records of the second execution.

    Returns
    -------
    dict
        ``activities`` keyed by activity_id with ``*_a``/``*_b``/``*_delta``
        columns, plus ``only_in_a``/``only_in_b`` and total bounds.
    """
    tasks_a, tasks_b = _tasks(records_a), _tasks(records_b)
    rows_a = {r["activity_id"]: r for r in group_activities(tasks_a)}
    rows_b = {r["activity_id"]: r for r in group_activities(tasks_b)}

    def error_rate(row: Dict[str, Any]) -> Optional[float]:
        n = row.get("n_tasks") or 0
        if not n:
            return None
        errors = (row.get("status_counts") or {}).get(_STATUS_ERROR, 0)
        return round(errors / n, 4)

    activities: Dict[str, Dict[str, Any]] = {}
    for activity in sorted(set(rows_a) | set(rows_b)):
        a, b = rows_a.get(activity), rows_b.get(activity)
        count_a = a["n_tasks"] if a else 0
        count_b = b["n_tasks"] if b else 0
        avg_a = a.get("elapsed_avg") if a else None
        avg_b = b.get("elapsed_avg") if b else None
        rate_a = error_rate(a) if a else None
        rate_b = error_rate(b) if b else None
        activities[activity] = {
            "count_a": count_a,
            "count_b": count_b,
            "count_delta": count_b - count_a,
            "elapsed_avg_a": avg_a,
            "elapsed_avg_b": avg_b,
            "elapsed_avg_delta": (avg_b - avg_a) if avg_a is not None and avg_b is not None else None,
            "error_rate_a": rate_a,
            "error_rate_b": rate_b,
            "error_rate_delta": (rate_b - rate_a) if rate_a is not None and rate_b is not None else None,
        }

    _, _, total_a = workflow_bounds(tasks_a)
    _, _, total_b = workflow_bounds(tasks_b)
    return {
        "activities": activities,
        "only_in_a": sorted(set(rows_a) - set(rows_b)),
        "only_in_b": sorted(set(rows_b) - set(rows_a)),
        "totals": {
            "n_tasks_a": len(tasks_a),
            "n_tasks_b": len(tasks_b),
            "total_elapsed_a": total_a,
            "total_elapsed_b": total_b,
            "total_elapsed_delta": (total_b - total_a) if total_a is not None and total_b is not None else None,
        },
    }
