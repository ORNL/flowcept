"""Markdown renderer for campaign provenance-card reports.

Handles two campaign types automatically:

- **Replicated** (``campaign_type == "replicated"``): multiple runs of the same
  abstract workflow (same ``workflow.name``).  Focuses on cross-run comparison,
  timing trends, and execution host distribution.

- **Pipeline** (``campaign_type == "pipeline"``): multiple runs of different
  abstract workflows (different ``workflow.name``).  Focuses on stage ordering,
  per-stage mini-cards with hostname detail, and a unified artifact summary.

Both types follow the same template as the single-workflow provenance card:
    Title → Summary → Campaign-level Summary → Structure → Timing Report
    → Per Activity Details → Per-activity Resource Usage
    → Object Artifacts Summary → Footer
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from flowcept import __version__
from flowcept.report.aggregations import (
    as_float,
    extract_hostnames_from_workflow,
    fmt_timestamp_utc,
    group_activities,
    summarize_objects,
    workflow_bounds,
)
from flowcept.report.renderers.provenance_card_markdown import (
    _build_activity_io_summary,
    _build_per_activity_resource_section,
    _render_pipeline_structure,
    _timing_insights,
)


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------

def _to_str(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    return str(value)


def _fmt_seconds(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):.3f} s"


def _fmt_bytes(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(value)
    idx = 0
    while v >= 1024 and idx < len(units) - 1:
        v /= 1024.0
        idx += 1
    return f"{int(v)} {units[idx]}" if idx == 0 else f"{v:.2f} {units[idx]}"


def _short_id(wid: str, length: int = 8) -> str:
    return wid[:length] if wid and len(wid) >= length else wid


def _render_table(headers: List[str], rows: List[List[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in rows]
    if not body:
        body = ["| " + " | ".join(["-"] * len(headers)) + " |"]
    return "\n".join([head, sep] + body)


# ---------------------------------------------------------------------------
# Hostname helpers
# ---------------------------------------------------------------------------

_HOST_TOP_N = 10


def _render_host_distribution(host_counts: Counter, total_runs: int) -> List[str]:
    lines: List[str] = []
    unique = len(host_counts)
    lines.append(f"- **Unique hosts:** {unique}")
    lines.append(f"- **Total runs:** {total_runs}")
    top = host_counts.most_common(_HOST_TOP_N)
    rows = [[h, c, f"{100 * c / total_runs:.1f}%"] for h, c in top]
    lines.append("")
    lines.append(_render_table(["Hostname", "Runs", "% of total"], rows))
    if unique > _HOST_TOP_N:
        lines.append(f"\n_Showing top {_HOST_TOP_N} of {unique} hosts._")
    return lines


def _render_host_list(hostnames: List[str]) -> str:
    if not hostnames:
        return "-"
    return ", ".join(f"`{h}`" for h in hostnames)


# ---------------------------------------------------------------------------
# Section builders shared by both campaign types
# ---------------------------------------------------------------------------

def _render_summary_section(
    campaign_id: Optional[str],
    campaign_type: str,
    n_workflows: int,
    min_start: Optional[float],
    max_end: Optional[float],
    total_elapsed: Optional[float],
    extra_lines: List[str],
    lines: List[str],
) -> None:
    """Render the ``## Summary`` section (mirrors the single-workflow card)."""
    lines.append("## Summary")
    lines.append(f"- **Campaign ID:** `{_to_str(campaign_id)}`")
    if campaign_type == "pipeline":
        lines.append("- **Type:** Pipeline")
    lines.append(f"- **Workflow runs:** {n_workflows}")
    if min_start:
        lines.append(f"- **Execution Start (UTC):** `{fmt_timestamp_utc(min_start)}`")
    if max_end:
        lines.append(f"- **Execution End (UTC):** `{fmt_timestamp_utc(max_end)}`")
    if total_elapsed is not None:
        lines.append(f"- **Total Elapsed (s):** `{float(total_elapsed):.3f}`")
    for line in extra_lines:
        lines.append(line)
    lines.append("")


def _render_campaign_level_summary(
    workflows: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    total_elapsed: Optional[float],
    lines: List[str],
) -> None:
    """Render the ``## Campaign-level Summary`` section (mirrors Workflow-level Summary)."""
    activities = group_activities(tasks)
    total_task_count = len(tasks)
    status_counts: Dict[str, int] = {}
    for row in activities:
        for status, count in row["status_counts"].items():
            status_counts[status] = status_counts.get(status, 0) + int(count)

    lines.append("## Campaign-level Summary")
    lines.append(f"- **Total Activities:** `{len(activities)}`")
    lines.append(f"- **Total Tasks:** `{total_task_count}`")
    lines.append(f"- **Status Counts:** `{status_counts}`")
    if total_elapsed is not None:
        lines.append(f"- **Total Elapsed (s):** `{float(total_elapsed):.3f}`")

    # Top slowest activities (mirrors Workflow-level Summary top-5 slowest)
    top_slowest = sorted(
        [
            (_to_str(row.get("activity_id")), as_float(row.get("elapsed_median")))
            for row in activities
        ],
        key=lambda x: x[1] if x[1] is not None else -1,
        reverse=True,
    )[:5]
    slowest_items = [(name, sec) for name, sec in top_slowest if sec is not None]
    if len(activities) > 2 and slowest_items:
        lines.append("- **Top Slowest Activities:**")
        for name, sec in slowest_items:
            lines.append(f"  - `{name}`: `{sec:.3f} s`")
    lines.append("")


def _render_footer(lines: List[str]) -> None:
    """Append the standard ``---`` footer (mirrors the single-workflow card footer)."""
    generated_at = datetime.now().astimezone().strftime("%b %d, %Y at %I:%M %p %Z")
    lines.append("---")
    lines.append(
        "Workflow provenance card generated by "
        "[Flowcept](https://flowcept.org/) | "
        "[GitHub](https://github.com/ORNL/flowcept) | "
        f"[Version: {__version__}](https://github.com/ORNL/flowcept/releases/tag/v{__version__}) "
        f"on {generated_at}"
    )


# ---------------------------------------------------------------------------
# Type 1 — Replicated runs renderer
# ---------------------------------------------------------------------------

def _render_replicated(
    workflows: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    objects: List[Dict[str, Any]],
    campaign_id: Optional[str],
    lines: List[str],
) -> None:
    """Render sections specific to a replicated-run campaign."""
    workflow_name = _to_str(workflows[0].get("name") if workflows else None)
    min_start, max_end, total_elapsed = workflow_bounds(tasks)

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------
    lines.append("# Campaign Provenance Card — Replicated Runs")
    lines.append("")

    # ------------------------------------------------------------------
    # Section 1: Summary (mirrors ## Summary in single-workflow card)
    # ------------------------------------------------------------------
    _render_summary_section(
        campaign_id=campaign_id,
        campaign_type="replicated",
        n_workflows=len(workflows),
        min_start=min_start,
        max_end=max_end,
        total_elapsed=total_elapsed,
        extra_lines=[f"- **Workflow name:** `{workflow_name}`"] if workflow_name != "unknown" else [],
        lines=lines,
    )

    # ------------------------------------------------------------------
    # Section 2: Campaign-level Summary (mirrors ## Workflow-level Summary)
    # ------------------------------------------------------------------
    _render_campaign_level_summary(workflows, tasks, total_elapsed, lines)

    # ------------------------------------------------------------------
    # Section 3: Workflow Structure (abstract activity DAG, same as single-workflow)
    # ------------------------------------------------------------------
    activities = group_activities(tasks)
    lines.append(_render_pipeline_structure(activities))
    lines.append("")

    # ------------------------------------------------------------------
    # Section 4: Run Timing Report (mirrors ## Timing Report)
    # ------------------------------------------------------------------
    lines.append("## Run Timing Report")
    lines.append("Rows are sorted by **First Started At** (ascending).")
    lines.append("")

    tasks_by_wid: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        wid = str(t.get("workflow_id", "unknown"))
        tasks_by_wid.setdefault(wid, []).append(t)

    rows = []
    elapsed_per_run: List[Optional[float]] = []
    for i, wf in enumerate(workflows, 1):
        wid = str(wf.get("workflow_id", ""))
        wf_tasks = tasks_by_wid.get(wid, [])
        wf_min, wf_max, wf_elapsed = workflow_bounds(wf_tasks)
        status_counts = Counter(str(t.get("status", "unknown")) for t in wf_tasks)
        status_str = ", ".join(f"{s}:{c}" for s, c in sorted(status_counts.items())) or "-"
        rows.append([
            i,
            f"`{_short_id(wid)}`",
            fmt_timestamp_utc(wf_min) if wf_min else "-",
            _fmt_seconds(wf_elapsed),
            status_str,
        ])
        elapsed_per_run.append(wf_elapsed)

    lines.append(_render_table(
        ["Run #", "Workflow ID", "Started (UTC)", "Elapsed", "Status counts"],
        rows,
    ))
    lines.append("")

    # Timing insights (same subsection as single-workflow card)
    lines.extend(_timing_insights(activities))
    lines.append("")

    # ------------------------------------------------------------------
    # Section 5: Timing Trend (cross-run statistics, unique to replicated)
    # ------------------------------------------------------------------
    valid_elapsed = [e for e in elapsed_per_run if e is not None]
    if valid_elapsed:
        lines.append("## Timing Trend")
        lines.append("")
        lines.append(f"- **Fastest run:** {_fmt_seconds(min(valid_elapsed))}")
        lines.append(f"- **Slowest run:** {_fmt_seconds(max(valid_elapsed))}")
        n = len(valid_elapsed)
        mid = n // 2
        sorted_e = sorted(valid_elapsed)
        median = sorted_e[mid] if n % 2 == 1 else (sorted_e[mid - 1] + sorted_e[mid]) / 2.0
        lines.append(f"- **Median run:** {_fmt_seconds(median)}")
        if n >= 2:
            delta = valid_elapsed[-1] - valid_elapsed[0]
            direction = "slower" if delta > 0 else "faster"
            lines.append(f"- **First → last delta:** {_fmt_seconds(abs(delta))} {direction}")
        lines.append("")

    # ------------------------------------------------------------------
    # Section 6: Per Activity Details (aggregated across all runs —
    #   same function as single-workflow card, tasks pooled from all runs)
    # ------------------------------------------------------------------
    tasks_sorted = sorted(tasks, key=lambda t: as_float(t.get("started_at")) or float("inf"))
    lines.extend(_build_activity_io_summary(tasks_sorted))

    # ------------------------------------------------------------------
    # Section 7: Per-activity Resource Usage (same as single-workflow card)
    # ------------------------------------------------------------------
    lines.extend(_build_per_activity_resource_section(tasks_sorted))

    # ------------------------------------------------------------------
    # Section 8: Execution Hosts (omitted when no hostname data available)
    # ------------------------------------------------------------------
    host_counts: Counter = Counter()
    for wf in workflows:
        for h in extract_hostnames_from_workflow(wf):
            host_counts[h] += 1
    if host_counts:
        lines.append("## Execution Hosts")
        lines.append("")
        lines.extend(_render_host_distribution(host_counts, len(workflows)))
        lines.append("")

    # ------------------------------------------------------------------
    # Section 9: Object Artifacts Summary
    # ------------------------------------------------------------------
    if objects:
        _render_object_summary(objects, lines)


# ---------------------------------------------------------------------------
# Type 2 — Pipeline renderer
# ---------------------------------------------------------------------------

def _render_pipeline_stage_flow(workflows: List[Dict[str, Any]]) -> str:
    """Render a linear stage-flow diagram for pipeline campaigns."""
    rail = "     │"
    down = "     ▼"
    stage_names = [_to_str(wf.get("name")) for wf in workflows]
    lines = ["   input", rail, down]
    for i, name in enumerate(stage_names):
        lines.append(f" {name}")
        if i < len(stage_names) - 1:
            lines.append(rail)
    lines.append(down)
    lines.append("   output")
    return "## Campaign Structure\n\n```text\n" + "\n".join(lines) + "\n```"


def _render_pipeline(
    workflows: List[Dict[str, Any]],
    tasks: List[Dict[str, Any]],
    objects: List[Dict[str, Any]],
    campaign_id: Optional[str],
    lines: List[str],
) -> None:
    """Render sections specific to a pipeline campaign."""
    min_start, max_end, total_elapsed = workflow_bounds(tasks)

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------
    lines.append("# Campaign Provenance Card — Pipeline")
    lines.append("")

    # ------------------------------------------------------------------
    # Section 1: Summary
    # ------------------------------------------------------------------
    _render_summary_section(
        campaign_id=campaign_id,
        campaign_type="pipeline",
        n_workflows=len(workflows),
        min_start=min_start,
        max_end=max_end,
        total_elapsed=total_elapsed,
        extra_lines=[],
        lines=lines,
    )

    # ------------------------------------------------------------------
    # Section 2: Campaign-level Summary
    # ------------------------------------------------------------------
    _render_campaign_level_summary(workflows, tasks, total_elapsed, lines)

    # ------------------------------------------------------------------
    # Section 3: Campaign Structure (linear stage flow)
    # ------------------------------------------------------------------
    lines.append(_render_pipeline_stage_flow(workflows))
    lines.append("")

    # ------------------------------------------------------------------
    # Section 4: Stage Overview (mirrors ## Timing Report)
    # ------------------------------------------------------------------
    lines.append("## Stage Overview")
    lines.append("Rows are sorted by **First Started At** (ascending).")
    lines.append("")

    tasks_by_wid: Dict[str, List[Dict[str, Any]]] = {}
    for t in tasks:
        wid = str(t.get("workflow_id", "unknown"))
        tasks_by_wid.setdefault(wid, []).append(t)

    overview_rows = []
    for i, wf in enumerate(workflows, 1):
        wid = str(wf.get("workflow_id", ""))
        name = _to_str(wf.get("name"))
        wf_tasks = tasks_by_wid.get(wid, [])
        wf_min, wf_max, wf_elapsed = workflow_bounds(wf_tasks)
        status_counts = Counter(str(t.get("status", "unknown")) for t in wf_tasks)
        status_str = ", ".join(f"{s}:{c}" for s, c in sorted(status_counts.items())) or "-"
        hostnames = extract_hostnames_from_workflow(wf)
        overview_rows.append([
            i,
            name,
            f"`{_short_id(wid)}`",
            fmt_timestamp_utc(wf_min) if wf_min else "-",
            _fmt_seconds(wf_elapsed),
            status_str,
            _render_host_list(hostnames),
        ])

    lines.append(_render_table(
        ["Stage #", "Workflow name", "Workflow ID", "Started (UTC)", "Elapsed", "Status counts", "Host(s)"],
        overview_rows,
    ))
    lines.append("")

    # ------------------------------------------------------------------
    # Section 5: Per-stage details
    #   Each stage follows the same sub-template as the single-workflow card:
    #   Summary → Per Activity Details → Per-activity Resource Usage
    # ------------------------------------------------------------------
    lines.append("## Stage Details")
    lines.append("")

    for i, wf in enumerate(workflows, 1):
        wid = str(wf.get("workflow_id", ""))
        name = _to_str(wf.get("name"))
        hostnames = extract_hostnames_from_workflow(wf)
        wf_tasks = tasks_by_wid.get(wid, [])
        wf_min, wf_max, wf_elapsed = workflow_bounds(wf_tasks)

        lines.append(f"### Stage {i}: `{name}`")
        lines.append("")
        lines.append(f"- **Workflow ID:** `{wid}`")
        lines.append(f"- **Elapsed:** {_fmt_seconds(wf_elapsed)}")
        if wf_min:
            lines.append(f"- **Started:** {fmt_timestamp_utc(wf_min)} UTC")
        if wf_max:
            lines.append(f"- **Ended:** {fmt_timestamp_utc(wf_max)} UTC")
        lines.append(f"- **Host(s):** {_render_host_list(hostnames)}")

        used = wf.get("used")
        generated = wf.get("generated")
        if used and isinstance(used, dict):
            used_str = ", ".join(f"`{k}`" for k in used.keys())
            lines.append(f"- **Used:** {used_str}")
        if generated and isinstance(generated, dict):
            gen_str = ", ".join(f"`{k}`" for k in generated.keys())
            lines.append(f"- **Generated:** {gen_str}")

        if wf_tasks:
            stage_tasks_sorted = sorted(wf_tasks, key=lambda t: as_float(t.get("started_at")) or float("inf"))
            lines.extend(_build_activity_io_summary(stage_tasks_sorted, heading="####"))
            lines.extend(_build_per_activity_resource_section(stage_tasks_sorted, heading="####"))

        lines.append("")

    # ------------------------------------------------------------------
    # Section 6: Object Artifacts Summary
    # ------------------------------------------------------------------
    if objects:
        _render_object_summary(objects, lines)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _render_object_summary(objects: List[Dict[str, Any]], lines: List[str]) -> None:
    """Append a compact object artifact summary section (mirrors single-workflow card)."""
    summary = summarize_objects(objects)
    if not summary["total_objects"]:
        return
    lines.append("## Object Artifacts Summary")
    lines.append("")
    lines.append(f"- **Total objects:** {summary['total_objects']}")
    if summary["by_type"]:
        by_type_str = ", ".join(f"{t}: {c}" for t, c in sorted(summary["by_type"].items()))
        lines.append(f"- **By type:** {by_type_str}")
    if summary["by_storage"]:
        by_storage_str = ", ".join(f"{s}: {c}" for s, c in sorted(summary["by_storage"].items()))
        lines.append(f"- **By storage:** {by_storage_str}")
    if summary["total_size_bytes"]:
        lines.append(f"- **Total size:** {_fmt_bytes(summary['total_size_bytes'])}")
    lines.append("")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def render_provenance_campaign_card_markdown(
    dataset: Dict[str, Any],
    output_path: Path,
) -> Dict[str, Any]:
    """Render a campaign provenance card and write it to ``output_path``.

    Parameters
    ----------
    dataset:
        Campaign-shaped dataset with keys ``campaign_id``, ``workflows``,
        ``tasks``, and ``objects``.
    output_path:
        Destination ``.md`` file path.

    Returns
    -------
    dict
        Render statistics: ``campaign_type``, ``n_workflows``, ``n_tasks``,
        ``n_objects``.
    """
    workflows: List[Dict[str, Any]] = dataset.get("workflows", [])
    tasks: List[Dict[str, Any]] = dataset.get("tasks", [])
    objects: List[Dict[str, Any]] = dataset.get("objects", [])
    campaign_id: Optional[str] = dataset.get("campaign_id")

    unique_names = {w.get("name") for w in workflows if w.get("name")}
    campaign_type = "replicated" if len(unique_names) <= 1 else "pipeline"

    lines: List[str] = []

    if campaign_type == "replicated":
        _render_replicated(workflows, tasks, objects, campaign_id, lines)
    else:
        _render_pipeline(workflows, tasks, objects, campaign_id, lines)

    _render_footer(lines)

    output_path = Path(output_path)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return {
        "campaign_type": campaign_type,
        "n_workflows": len(workflows),
        "n_tasks": len(tasks),
        "n_objects": len(objects),
    }
