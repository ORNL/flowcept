"""PDF renderer for Flowcept provenance reports."""

from __future__ import annotations

import html
import json
import math
import re
import textwrap
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, Iterable, List, Tuple

from flowcept import __version__
from flowcept.commons.vocabulary import ML_Types
from flowcept.report.aggregations import as_float, elapsed_seconds, fmt_timestamp_utc, workflow_bounds


def _to_str(value: Any, default: str = "unknown") -> str:
    """Convert any value to string with a default fallback."""
    if value is None:
        return default
    return str(value)


def _positive(value: float | None) -> float | None:
    """Keep positive values only."""
    if value is None:
        return None
    return value if value > 0 else None


def _fmt_seconds(value: float | None) -> str:
    """Format seconds."""
    if value is None:
        return "unknown"
    return f"{value:.3f}"


def _fmt_percent(value: float | None) -> str:
    """Format percentages."""
    v = _positive(value)
    if v is None:
        return "-"
    return f"{v:.1f}%"


def _fmt_count(value: float | None) -> str:
    """Format numeric counts."""
    v = _positive(value)
    if v is None:
        return "-"
    return f"{int(v):,}"


def _fmt_bytes(value: float | None) -> str:
    """Format byte values in human-readable units."""
    v = _positive(value)
    if v is None:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while v >= 1024 and idx < len(units) - 1:
        v /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(v)} {units[idx]}"
    return f"{v:.2f} {units[idx]}"


def _is_empty(value: Any) -> bool:
    """Return True when value should be hidden in report output."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"", "-", "unknown", "- / -"}
    return False


def _add_summary_bullet(story: List[Any], label: str, value: Any, style: Any) -> None:
    """Add summary bullet only when value is meaningful."""
    if _is_empty(value):
        return
    _add_bullet(story, f"**{label}:** `{value}`", style)


def _deep_get(dct: Dict[str, Any], path: List[str]) -> Any:
    """Read nested dictionary path safely."""
    cur: Any = dct
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _delta(a: Any, b: Any) -> float | None:
    """Compute numeric delta b-a."""
    av = as_float(a)
    bv = as_float(b)
    if av is None or bv is None:
        return None
    return bv - av


def _extract_io_bytes(task: Dict[str, Any]) -> float:
    """Extract total read+write bytes for a task from telemetry snapshots."""
    start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
    end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
    read_b = _delta(
        _deep_get(start, ["disk", "io_sum", "read_bytes"]), _deep_get(end, ["disk", "io_sum", "read_bytes"])
    )
    write_b = _delta(
        _deep_get(start, ["disk", "io_sum", "write_bytes"]), _deep_get(end, ["disk", "io_sum", "write_bytes"])
    )
    return max(0.0, read_b or 0.0) + max(0.0, write_b or 0.0)


def _render_inline(text: str) -> str:
    """Render inline text with links and backtick highlighting for ReportLab paragraphs."""
    cleaned = text.replace("<br>", " ").replace("<br/>", " ").replace("**", "").strip()

    def _code_spans(chunk: str) -> str:
        parts: List[str] = []
        last = 0
        for match in re.finditer(r"`([^`]+)`", chunk):
            start, end = match.span()
            if start > last:
                parts.append(html.escape(chunk[last:start]))
            code_text = html.escape(match.group(1))
            parts.append(f'<font name="Courier" backcolor="#f8fafc">{code_text}</font>')
            last = end
        if last < len(chunk):
            parts.append(html.escape(chunk[last:]))
        return "".join(parts)

    out: List[str] = []
    last = 0
    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", cleaned):
        start, end = match.span()
        if start > last:
            out.append(_code_spans(cleaned[last:start]))
        href = html.escape(match.group(2), quote=True)
        link_text = _code_spans(match.group(1))
        out.append(f'<link href="{href}" color="blue">{link_text}</link>')
        last = end
    if last < len(cleaned):
        out.append(_code_spans(cleaned[last:]))
    return "".join(out)


def _insert_breaks_for_long_tokens(text: str, chunk: int = 18) -> str:
    """Insert line breaks in very long tokens to avoid overflow."""

    def _split(match: re.Match[str]) -> str:
        token = match.group(0)
        return "<br/>".join(token[i : i + chunk] for i in range(0, len(token), chunk))

    return re.sub(r"\S{30,}", _split, text)


def _flatten_numeric(prefix: str, value: Any, out: Dict[str, float]) -> None:
    """Flatten nested values and keep numeric leaves only."""
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else str(k)
            _flatten_numeric(child, v, out)
        return
    if isinstance(value, list):
        for idx, v in enumerate(value):
            child = f"{prefix}[{idx}]"
            _flatten_numeric(child, v, out)
        return
    num = as_float(value)
    if num is not None:
        out[prefix] = num


def _compute_telemetry_delta(start: Dict[str, Any], end: Dict[str, Any]) -> Dict[str, float | None]:
    """Compute per-task telemetry deltas between start and end snapshots."""
    return {
        "cpu_user": _positive(
            _delta(_deep_get(start, ["cpu", "times_avg", "user"]), _deep_get(end, ["cpu", "times_avg", "user"]))
        ),
        "cpu_system": _positive(
            _delta(_deep_get(start, ["cpu", "times_avg", "system"]), _deep_get(end, ["cpu", "times_avg", "system"]))
        ),
        "cpu_percent": _positive(
            _delta(_deep_get(start, ["cpu", "percent_all"]), _deep_get(end, ["cpu", "percent_all"]))
        ),
        "memory_used": _positive(
            _delta(_deep_get(start, ["memory", "virtual", "used"]), _deep_get(end, ["memory", "virtual", "used"]))
        ),
        "read_bytes": _positive(
            _delta(_deep_get(start, ["disk", "io_sum", "read_bytes"]), _deep_get(end, ["disk", "io_sum", "read_bytes"]))
        ),
        "write_bytes": _positive(
            _delta(
                _deep_get(start, ["disk", "io_sum", "write_bytes"]), _deep_get(end, ["disk", "io_sum", "write_bytes"])
            )
        ),
        "read_count": _positive(
            _delta(_deep_get(start, ["disk", "io_sum", "read_count"]), _deep_get(end, ["disk", "io_sum", "read_count"]))
        ),
        "write_count": _positive(
            _delta(
                _deep_get(start, ["disk", "io_sum", "write_count"]), _deep_get(end, ["disk", "io_sum", "write_count"])
            )
        ),
    }


def _extract_telemetry_overview(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate workflow-level telemetry usage from all tasks."""
    totals = defaultdict(float)
    cpu_percent_values: List[float] = []
    memory_percent_values: List[float] = []
    swap_percent_values: List[float] = []
    cpu_freq_values: List[float] = []

    for task in tasks:
        start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
        end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
        if not start and not end:
            continue

        delta = _compute_telemetry_delta(start, end)
        for key in ["cpu_user", "cpu_system", "memory_used", "read_bytes", "write_bytes", "read_count", "write_count"]:
            totals[key] += delta.get(key) or 0.0

        if delta.get("cpu_percent") is not None:
            cpu_percent_values.append(float(delta["cpu_percent"]))

        vm_percent = as_float(_deep_get(end, ["memory", "virtual", "percent"]))
        sw_percent = as_float(_deep_get(end, ["memory", "swap", "percent"]))
        cpu_freq = as_float(_deep_get(end, ["cpu", "frequency"]))
        if vm_percent is not None:
            memory_percent_values.append(vm_percent)
        if sw_percent is not None:
            swap_percent_values.append(sw_percent)
        if cpu_freq is not None:
            cpu_freq_values.append(cpu_freq)

        totals["disk_read_time"] += (
            _delta(_deep_get(start, ["disk", "io_sum", "read_time"]), _deep_get(end, ["disk", "io_sum", "read_time"]))
            or 0.0
        )
        totals["disk_write_time"] += (
            _delta(_deep_get(start, ["disk", "io_sum", "write_time"]), _deep_get(end, ["disk", "io_sum", "write_time"]))
            or 0.0
        )
        totals["disk_busy_time"] += (
            _delta(_deep_get(start, ["disk", "io_sum", "busy_time"]), _deep_get(end, ["disk", "io_sum", "busy_time"]))
            or 0.0
        )

    return {
        "samples": sum(
            1
            for t in tasks
            if isinstance(t.get("telemetry_at_start"), dict) and isinstance(t.get("telemetry_at_end"), dict)
        ),
        "cpu_user": totals["cpu_user"] or None,
        "cpu_system": totals["cpu_system"] or None,
        "cpu_percent_avg": (sum(cpu_percent_values) / len(cpu_percent_values)) if cpu_percent_values else None,
        "cpu_frequency_avg": (sum(cpu_freq_values) / len(cpu_freq_values)) if cpu_freq_values else None,
        "memory_used": totals["memory_used"] or None,
        "memory_percent_avg": (sum(memory_percent_values) / len(memory_percent_values))
        if memory_percent_values
        else None,
        "swap_percent_avg": (sum(swap_percent_values) / len(swap_percent_values)) if swap_percent_values else None,
        "read_bytes": totals["read_bytes"] or None,
        "write_bytes": totals["write_bytes"] or None,
        "read_count": totals["read_count"] or None,
        "write_count": totals["write_count"] or None,
        "disk_read_time": totals["disk_read_time"] or None,
        "disk_write_time": totals["disk_write_time"] or None,
        "disk_busy_time": totals["disk_busy_time"] or None,
    }


def _status_counts(tasks: List[Dict[str, Any]]) -> Dict[str, int]:
    """Return workflow-level status counts."""
    return dict(Counter(_to_str(task.get("status")) for task in tasks))


def _timing_rows(activities: List[Dict[str, Any]]) -> List[List[str]]:
    """Build timing report rows from aggregated activity records."""
    rows = [["Activity", "Status Counts", "First Started At", "Last Ended At", "Median Elapsed (s)"]]
    for activity in activities:
        rows.append(
            [
                _to_str(activity.get("activity_id")),
                _to_str(activity.get("status_counts")),
                fmt_timestamp_utc(activity.get("started_at_min")),
                fmt_timestamp_utc(activity.get("ended_at_max")),
                _fmt_seconds(as_float(activity.get("elapsed_median"))),
            ]
        )
    return rows


def _timing_insights(activities: List[Dict[str, Any]]) -> List[str]:
    """Build timing insights from activity medians."""
    values = [(_to_str(a.get("activity_id")), as_float(a.get("elapsed_median"))) for a in activities]
    values = [(name, val) for name, val in values if val is not None]
    if not values:
        return ["No valid elapsed timings were available."]
    slowest = sorted(values, key=lambda item: item[1], reverse=True)[:5]
    fastest = sorted(values, key=lambda item: item[1])[:3]
    return [
        "Slowest activities: " + ", ".join(f"`{name}` ({elapsed:.3f}s)" for name, elapsed in slowest),
        "Fastest activities: " + ", ".join(f"`{name}` ({elapsed:.3f}s)" for name, elapsed in fastest),
    ]


def _resource_rows(tasks: List[Dict[str, Any]]) -> List[List[str]]:
    """Build per-activity aggregated resource usage rows."""
    rows = [
        [
            "Activity",
            "Elapsed (s)",
            "CPU User (s)",
            "CPU System (s)",
            "CPU (%)",
            "Memory Delta",
            "Read",
            "Write",
            "Read Ops",
            "Write Ops",
        ]
    ]
    ordered = sorted(tasks, key=lambda task: as_float(task.get("started_at")) or float("inf"))
    activity_order: List[str] = []
    activity_elapsed: Dict[str, List[float]] = defaultdict(list)
    activity_cpu_user: Dict[str, float] = defaultdict(float)
    activity_cpu_system: Dict[str, float] = defaultdict(float)
    activity_cpu_percent: Dict[str, List[float]] = defaultdict(list)
    activity_memory: Dict[str, float] = defaultdict(float)
    activity_read: Dict[str, float] = defaultdict(float)
    activity_write: Dict[str, float] = defaultdict(float)
    activity_read_ops: Dict[str, float] = defaultdict(float)
    activity_write_ops: Dict[str, float] = defaultdict(float)

    for task in ordered:
        activity = _to_str(task.get("activity_id"))
        if activity not in activity_order:
            activity_order.append(activity)
        start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
        end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
        delta = _compute_telemetry_delta(start, end)
        elapsed_value = elapsed_seconds(task.get("started_at"), task.get("ended_at"))
        if elapsed_value is not None:
            activity_elapsed[activity].append(elapsed_value)
        activity_cpu_user[activity] += delta.get("cpu_user") or 0.0
        activity_cpu_system[activity] += delta.get("cpu_system") or 0.0
        activity_memory[activity] += delta.get("memory_used") or 0.0
        activity_read[activity] += delta.get("read_bytes") or 0.0
        activity_write[activity] += delta.get("write_bytes") or 0.0
        activity_read_ops[activity] += delta.get("read_count") or 0.0
        activity_write_ops[activity] += delta.get("write_count") or 0.0
        if delta.get("cpu_percent") is not None:
            activity_cpu_percent[activity].append(delta.get("cpu_percent"))

    for activity in activity_order:
        elapsed_values = sorted(activity_elapsed.get(activity, []))
        elapsed_median = _percentile(elapsed_values, 0.5) if elapsed_values else None
        cpu_percent_values = activity_cpu_percent.get(activity, [])
        cpu_percent_avg = (sum(cpu_percent_values) / len(cpu_percent_values)) if cpu_percent_values else None
        rows.append(
            [
                activity,
                _fmt_seconds(elapsed_median),
                _fmt_seconds(activity_cpu_user.get(activity)),
                _fmt_seconds(activity_cpu_system.get(activity)),
                _fmt_percent(cpu_percent_avg),
                _fmt_bytes(activity_memory.get(activity)),
                _fmt_bytes(activity_read.get(activity)),
                _fmt_bytes(activity_write.get(activity)),
                _fmt_count(activity_read_ops.get(activity)),
                _fmt_count(activity_write_ops.get(activity)),
            ]
        )
    return rows


def _resource_insights(tasks: List[Dict[str, Any]]) -> List[str]:
    """Build per-activity aggregated resource insights."""
    activity_order: List[str] = []
    activity_read: Dict[str, float] = defaultdict(float)
    activity_write: Dict[str, float] = defaultdict(float)
    activity_cpu_percent: Dict[str, List[float]] = defaultdict(list)
    activity_memory: Dict[str, float] = defaultdict(float)
    for task in sorted(tasks, key=lambda task: as_float(task.get("started_at")) or float("inf")):
        activity = _to_str(task.get("activity_id"))
        if activity not in activity_order:
            activity_order.append(activity)
        start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
        end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
        delta = _compute_telemetry_delta(start, end)
        activity_read[activity] += delta.get("read_bytes") or 0.0
        activity_write[activity] += delta.get("write_bytes") or 0.0
        activity_memory[activity] += delta.get("memory_used") or 0.0
        if delta.get("cpu_percent") is not None:
            activity_cpu_percent[activity].append(delta.get("cpu_percent"))

    insights: List[str] = []
    io_rank = [
        (activity, activity_read.get(activity, 0.0), activity_write.get(activity, 0.0)) for activity in activity_order
    ]
    io_top = sorted(io_rank, key=lambda row: row[1] + row[2], reverse=True)[:5]
    if io_top:
        insights.append("Most IO-heavy Activities (Read + Write):")
        insights.extend(
            [f"`{name}`: Read={_fmt_bytes(read_b)}, Write={_fmt_bytes(write_b)}" for name, read_b, write_b in io_top]
        )

    cpu_rank = [
        (
            activity,
            (
                (sum(activity_cpu_percent.get(activity, [])) / len(activity_cpu_percent.get(activity, [])))
                if activity_cpu_percent.get(activity)
                else 0.0
            ),
        )
        for activity in activity_order
    ]
    cpu_top = [(name, cpu) for name, cpu in sorted(cpu_rank, key=lambda row: row[1], reverse=True)[:5] if cpu > 0]
    if cpu_top:
        insights.append("Most CPU-active Activities:")
        insights.extend([f"`{name}`: CPU={_fmt_percent(cpu)}" for name, cpu in cpu_top])

    memory_rank = [(activity, activity_memory.get(activity, 0.0)) for activity in activity_order]
    memory_top = [(name, mem) for name, mem in sorted(memory_rank, key=lambda row: row[1], reverse=True)[:5] if mem > 0]
    if memory_top:
        insights.append("Largest memory growth Activities:")
        insights.extend([f"`{name}`: Memory Delta={_fmt_bytes(mem)}" for name, mem in memory_top])

    return insights


def _group_by_activity(tasks: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group task records by activity_id."""
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[_to_str(task.get("activity_id"))].append(task)
    return grouped


def _safe_repr(value: Any, limit: int = 180) -> str:
    """Return compact representation for values in details sections."""
    try:
        if isinstance(value, (dict, list, tuple)):
            text = json.dumps(value, ensure_ascii=False)
        else:
            text = str(value)
    except Exception:
        text = str(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _percentile(values: List[float], percentile: float) -> float:
    """Compute percentile with linear interpolation."""
    if len(values) == 1:
        return values[0]
    idx = (len(values) - 1) * percentile
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return values[lo]
    frac = idx - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def _summarize_values(values: List[Any], total: int) -> str:
    """Summarize aggregated activity field values."""
    presence = f"{(len(values) / total) * 100:.1f}%"
    numeric = [as_float(v) for v in values]
    numeric = [v for v in numeric if v is not None]
    if numeric and len(numeric) == len(values):
        numeric.sort()
        return (
            f"presence={presence}; type=numeric; min={numeric[0]:.3f}; "
            f"p50={_percentile(numeric, 0.5):.3f}; p95={_percentile(numeric, 0.95):.3f}; max={numeric[-1]:.3f}"
        )
    top = Counter(_safe_repr(v, 60) for v in values).most_common(3)
    return f"presence={presence}; type=scalar/categorical; top_values=" + ", ".join(
        f"{val} ({count})" for val, count in top
    )


def _activity_detail_lines(records: List[Dict[str, Any]], activity_id: str) -> List[str]:
    """Build lines for per-activity details."""
    lines: List[str] = []
    subtype = _to_str((records[0].get("subtype") if records else None), "unknown")
    has_subtype = bool(subtype and subtype != "unknown")
    if len(records) > 1:
        if has_subtype:
            lines.append(f"**{activity_id}** (`n={len(records)}`, subtype=`{subtype}`)")
        else:
            lines.append(f"**{activity_id}** (`n={len(records)}`)")
    else:
        if has_subtype:
            lines.append(f"**{activity_id}** (subtype=`{subtype}`)")
        else:
            lines.append(f"**{activity_id}**")
        tags = records[0].get("tags") if records else None
        if isinstance(tags, list) and len(tags) > 0:
            if len(tags) == 1:
                lines.append(f"Tag: `{_safe_repr(tags[0], 120)}`")
            else:
                tag_values = ", ".join(f"`{_safe_repr(tag, 80)}`" for tag in tags)
                lines.append(f"Tags: {tag_values}")

    used_values: Dict[str, List[Any]] = defaultdict(list)
    generated_values: Dict[str, List[Any]] = defaultdict(list)
    for record in records:
        used = record.get("used", {}) if isinstance(record.get("used"), dict) else {}
        generated = record.get("generated", {}) if isinstance(record.get("generated"), dict) else {}
        for key, value in used.items():
            used_values[key].append(value)
        for key, value in generated.items():
            generated_values[key].append(value)

    if len(records) == 1:
        if used_values:
            lines.append("Used:")
            for key in sorted(used_values.keys())[:20]:
                lines.append(f"`{key}`: `{_safe_repr(used_values[key][0])}`")
        if generated_values:
            lines.append("Generated:")
            for key in sorted(generated_values.keys())[:20]:
                lines.append(f"`{key}`: `{_safe_repr(generated_values[key][0])}`")
        return lines

    if used_values:
        lines.append("Used (aggregated):")
        for key in sorted(used_values.keys())[:20]:
            lines.append(f"`{key}`: {_summarize_values(used_values[key], len(records))}")

    if generated_values:
        lines.append("Generated (aggregated):")
        for key in sorted(generated_values.keys())[:20]:
            lines.append(f"`{key}`: {_summarize_values(generated_values[key], len(records))}")

    return lines


def _activity_detail_insights(tasks: List[Dict[str, Any]]) -> List[str]:
    """Build per-activity used/generated variability insights."""
    grouped = _group_by_activity(tasks)
    used_richness = []
    generated_richness = []
    variability: List[Tuple[str, float]] = []

    for activity_id, records in grouped.items():
        used_fields = set()
        generated_fields = set()
        field_values: Dict[str, List[float]] = defaultdict(list)

        for record in records:
            used = record.get("used", {}) if isinstance(record.get("used"), dict) else {}
            generated = record.get("generated", {}) if isinstance(record.get("generated"), dict) else {}
            used_fields.update(used.keys())
            generated_fields.update(generated.keys())

            for section, data in (("used", used), ("generated", generated)):
                for key, value in data.items():
                    numeric = as_float(value)
                    if numeric is not None:
                        field_values[f"{activity_id}:{section}.{key}"].append(numeric)

        used_richness.append((activity_id, len(used_fields)))
        generated_richness.append((activity_id, len(generated_fields)))

        for field_name, nums in field_values.items():
            if not nums:
                continue
            variability.append((field_name, max(nums) - min(nums)))

    lines: List[str] = []
    used_top = [item for item in sorted(used_richness, key=lambda row: row[1], reverse=True) if item[1] > 0][:5]
    if used_top:
        lines.append(
            "Activities with richest **used** metadata: "
            + ", ".join(f"`{name}` ({count} fields)" for name, count in used_top)
        )

    generated_top = [item for item in sorted(generated_richness, key=lambda row: row[1], reverse=True) if item[1] > 0][
        :5
    ]
    if generated_top:
        lines.append(
            "Activities with richest **generated** metadata: "
            + ", ".join(f"`{name}` ({count} fields)" for name, count in generated_top)
        )

    variability_top = sorted(variability, key=lambda row: row[1], reverse=True)[:5]
    if variability_top:
        lines.append(
            "Highest numeric variability fields: "
            + ", ".join(f"`{field}` (range={rng:.3f})" for field, rng in variability_top)
        )

    return lines


def _workflow_structure_text(
    activities: List[Dict[str, Any]], input_label: str = " input data", output_label: str = " output data"
) -> str:
    """Build ascii workflow structure for unique activities."""
    rail = "        │"
    down = "        ▼"
    lines = [input_label, rail, down]
    for index, activity in enumerate(activities):
        lines.append(f" {_to_str(activity.get('activity_id'))}")
        if index < len(activities) - 1:
            lines.append(rail)
    lines.append(down)
    lines.append(output_label)
    return "\n".join(lines)


def _normalize_flow_label(name: str) -> str:
    """Normalize workflow node labels for better visual rendering."""
    return " ".join(name.replace("_", " ").split())


def _render_workflow_structure_plot_nodes(nodes: List[str], output_path: Path) -> None:
    """Render a left-to-right workflow structure plot with rectangular nodes."""
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch

    labels = [_normalize_flow_label(node) for node in nodes]
    is_terminal = [idx == 0 or idx == len(nodes) - 1 for idx in range(len(nodes))]
    wrapped_lines = [
        textwrap.wrap(label, width=18, break_long_words=True, break_on_hyphens=True) or [label] for label in labels
    ]
    wrapped = ["\n".join(lines) for lines in wrapped_lines]

    node_height = 0.2  # uniform height for all activity boxes
    gap = 0.5
    widths: List[float] = []
    for idx, lines in enumerate(wrapped_lines):
        max_len = max(len(line) for line in lines) if lines else 1
        if is_terminal[idx]:
            widths.append(max(1.1, min(2.1, 0.10 * max_len + 0.45)))
        else:
            widths.append(max(1.45, min(3.55, 0.12 * max_len + 0.72)))

    x_positions: List[float] = []
    cursor = 0.0
    for idx, width in enumerate(widths):
        if idx == 0:
            center = width / 2.0
        else:
            prev_width = widths[idx - 1]
            center = cursor + prev_width / 2.0 + gap + width / 2.0
        x_positions.append(center)
        cursor = center

    total_width = x_positions[-1] + widths[-1] / 2.0 if x_positions else 8.0
    fig_width = max(8.0, total_width * 0.82)
    fig, axis = plt.subplots(figsize=(fig_width, 2.45))
    fig.patch.set_facecolor("white")
    axis.set_facecolor("#f8fafc")

    for idx, text in enumerate(wrapped):
        x_center = x_positions[idx]
        width = widths[idx]
        if not is_terminal[idx]:
            rect = FancyBboxPatch(
                (x_center - width / 2.0, -node_height / 2.0),
                width,
                node_height,
                boxstyle="round,pad=0.05,rounding_size=0.08",
                linewidth=2.0,
                edgecolor="#0369a1",
                facecolor="#e2e8f0",
            )
            axis.add_patch(rect)
        axis.text(
            x_center,
            0.0,
            text,
            ha="center",
            va="center",
            fontsize=13.0,
            fontweight="bold",
            color="#0f172a",
        )

    for idx in range(len(nodes) - 1):
        start_x = x_positions[idx] + widths[idx] / 2.0 + 0.04
        end_x = x_positions[idx + 1] - widths[idx + 1] / 2.0 - 0.04
        axis.annotate(
            "",
            xy=(end_x, 0.0),
            xytext=(start_x, 0.0),
            arrowprops={"arrowstyle": "-|>", "color": "#0284c7", "lw": 2.2, "shrinkA": 0, "shrinkB": 0},
        )

    axis.set_xlim(-0.35, total_width + 0.35)
    axis.set_ylim(-0.52, 0.52)
    axis.set_axis_off()
    fig.tight_layout(pad=0.05)
    fig.savefig(output_path, dpi=360, bbox_inches="tight", pad_inches=0.01)
    plt.close(fig)


def _render_workflow_structure_plots(
    activities: List[Dict[str, Any]], output_dir: Path, max_activities_per_plot: int = 7
) -> List[Path]:
    """Render one or more workflow structure plots, chunked to avoid overflow."""
    activity_names = [_to_str(activity.get("activity_id")) for activity in activities]
    if not activity_names:
        path = output_dir / "workflow_structure_1.png"
        _render_workflow_structure_plot_nodes(["input data", "output data"], path)
        return [path]

    paths: List[Path] = []
    for idx, start in enumerate(range(0, len(activity_names), max_activities_per_plot), start=1):
        chunk = activity_names[start : start + max_activities_per_plot]
        left = "input data" if start == 0 else "continued"
        right = "output data" if (start + max_activities_per_plot) >= len(activity_names) else "continued"
        nodes = [left] + chunk + [right]
        path = output_dir / f"workflow_structure_{idx}.png"
        _render_workflow_structure_plot_nodes(nodes, path)
        paths.append(path)
    return paths


def _object_type_label(obj_type: str) -> str:
    """Map object type values to display labels."""
    normalized = obj_type.lower().strip()
    if normalized in {"ml_model", "model"}:
        return "Models"
    if normalized in {"dataset", "data_set"}:
        return "Datasets"
    return obj_type.replace("_", " ").title() + "s"


def _object_timestamp(obj: Dict[str, Any]) -> str:
    """Pick the best available timestamp from an object record."""
    for key in ["updated_at", "created_at", "utc_timestamp", "timestamp"]:
        ts = as_float(obj.get(key))
        if ts is not None:
            return fmt_timestamp_utc(ts)
    return "unknown"


def _scalar_lines(value: Any) -> List[str]:
    """Format scalar values, preserving multiline text blocks."""
    if isinstance(value, str):
        if "\n" not in value:
            return [value]
        lines = ["|"]
        lines.extend([f"  {row}" for row in value.splitlines()])
        return lines
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["true" if value else "false"]
    return [str(value)]


def _format_yaml_like_lines(value: Any, indent: int = 0) -> List[str]:
    """Render nested metadata as YAML-like indented lines."""
    pad = " " * indent

    if isinstance(value, dict):
        if not value:
            return [f"{pad}{{}}"]
        lines: List[str] = []
        for key in sorted(value.keys(), key=str):
            child = value[key]
            if isinstance(child, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_format_yaml_like_lines(child, indent=indent + 2))
                continue
            scalar = _scalar_lines(child)
            if len(scalar) == 1:
                lines.append(f"{pad}{key}: {scalar[0]}")
            else:
                lines.append(f"{pad}{key}: {scalar[0]}")
                lines.extend([f"{pad}{line}" for line in scalar[1:]])
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{pad}[]"]
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_format_yaml_like_lines(item, indent=indent + 2))
            else:
                scalar = _scalar_lines(item)
                if len(scalar) == 1:
                    lines.append(f"{pad}- {scalar[0]}")
                else:
                    lines.append(f"{pad}- {scalar[0]}")
                    lines.extend([f"{pad}  {line}" for line in scalar[1:]])
        return lines

    scalar = _scalar_lines(value)
    return [f"{pad}{line}" for line in scalar]


def _build_plot_data(
    activities: List[Dict[str, Any]], tasks: List[Dict[str, Any]]
) -> List[Tuple[str, List[str], List[float], str]]:
    """Build bar-plot definitions for report plots section."""
    slowest = [a for a in activities if as_float(a.get("elapsed_median")) is not None]
    slowest = sorted(slowest, key=lambda row: float(row.get("elapsed_median") or 0.0), reverse=True)[:5]

    fastest = [
        a
        for a in activities
        if as_float(a.get("elapsed_median")) is not None and float(a.get("elapsed_median") or 0.0) > 0
    ]
    fastest = sorted(fastest, key=lambda row: float(row.get("elapsed_median") or 0.0))[:5]

    io_by_activity: Dict[str, float] = {}
    for task in tasks:
        activity = _to_str(task.get("activity_id"))
        io_by_activity[activity] = io_by_activity.get(activity, 0.0) + _extract_io_bytes(task)
    io_top = sorted(io_by_activity.items(), key=lambda item: item[1], reverse=True)[:5]

    charts: List[Tuple[str, List[str], List[float], str]] = []
    if slowest:
        charts.append(
            (
                "Top Slowest Activities (Median Elapsed Seconds)",
                [_to_str(row.get("activity_id")) for row in slowest],
                [float(row.get("elapsed_median") or 0.0) for row in slowest],
                "Seconds",
            )
        )
    if fastest:
        charts.append(
            (
                "Top Fastest Activities (Median Elapsed Seconds)",
                [_to_str(row.get("activity_id")) for row in fastest],
                [float(row.get("elapsed_median") or 0.0) for row in fastest],
                "Seconds",
            )
        )
    if io_top:
        charts.append(
            (
                "Most Resource-Demanding Activities (Total IO Bytes)",
                [name for name, _ in io_top],
                [float(total) for _, total in io_top],
                "IO Bytes",
            )
        )

    charts.extend(_build_telemetry_plot_data(tasks))
    return charts


def _build_telemetry_plot_data(tasks: Iterable[Dict[str, Any]]) -> List[Tuple[str, List[str], List[float], str]]:
    """Build telemetry-specific plot definitions when telemetry data exists."""
    cpu_by_activity: Dict[str, List[float]] = {}
    memory_by_activity: Dict[str, float] = {}
    network_by_activity: Dict[str, float] = {}
    gpu_by_activity: Dict[str, float] = {}

    for task in tasks:
        activity = _to_str(task.get("activity_id"))
        start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
        end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
        if not start and not end:
            continue

        cpu_delta = _delta(_deep_get(start, ["cpu", "percent_all"]), _deep_get(end, ["cpu", "percent_all"])) or 0.0
        if cpu_delta > 0:
            cpu_by_activity.setdefault(activity, []).append(cpu_delta)

        memory_delta = (
            _delta(_deep_get(start, ["memory", "virtual", "used"]), _deep_get(end, ["memory", "virtual", "used"]))
            or 0.0
        )
        if memory_delta > 0:
            memory_by_activity[activity] = memory_by_activity.get(activity, 0.0) + memory_delta

        sent_delta = (
            _delta(
                _deep_get(start, ["network", "netio_sum", "bytes_sent"]),
                _deep_get(end, ["network", "netio_sum", "bytes_sent"]),
            )
            or 0.0
        )
        recv_delta = (
            _delta(
                _deep_get(start, ["network", "netio_sum", "bytes_recv"]),
                _deep_get(end, ["network", "netio_sum", "bytes_recv"]),
            )
            or 0.0
        )
        network_delta = max(0.0, sent_delta) + max(0.0, recv_delta)
        if network_delta > 0:
            network_by_activity[activity] = network_by_activity.get(activity, 0.0) + network_delta

        start_gpu = start.get("gpu", {}) if isinstance(start.get("gpu"), dict) else {}
        end_gpu = end.get("gpu", {}) if isinstance(end.get("gpu"), dict) else {}
        gpu_delta = 0.0
        for gpu_key, gpu_end in end_gpu.items():
            if not isinstance(gpu_end, dict):
                continue
            end_flat: Dict[str, float] = {}
            start_flat: Dict[str, float] = {}
            _flatten_numeric("", gpu_end, end_flat)
            _flatten_numeric(
                "", start_gpu.get(gpu_key, {}) if isinstance(start_gpu.get(gpu_key), dict) else {}, start_flat
            )
            for metric_name, metric_end in end_flat.items():
                metric_name_lower = metric_name.lower()
                if "used" not in metric_name_lower or "gpu" in metric_name_lower:
                    continue
                metric_start = start_flat.get(metric_name, 0.0)
                gpu_delta += metric_end - metric_start if metric_end >= metric_start else metric_end
        if gpu_delta > 0:
            gpu_by_activity[activity] = gpu_by_activity.get(activity, 0.0) + gpu_delta

    charts: List[Tuple[str, List[str], List[float], str]] = []
    cpu_top = sorted(
        ((name, sum(vals) / len(vals)) for name, vals in cpu_by_activity.items() if vals),
        key=lambda row: row[1],
        reverse=True,
    )[:5]
    if cpu_top:
        charts.append(
            (
                "Most CPU-Active Activities (Average CPU % Delta)",
                [name for name, _ in cpu_top],
                [value for _, value in cpu_top],
                "%",
            )
        )

    memory_top = sorted(memory_by_activity.items(), key=lambda row: row[1], reverse=True)[:5]
    if memory_top:
        charts.append(
            (
                "Largest Memory Growth Activities",
                [name for name, _ in memory_top],
                [value for _, value in memory_top],
                "Bytes",
            )
        )

    network_top = sorted(network_by_activity.items(), key=lambda row: row[1], reverse=True)[:5]
    if network_top:
        charts.append(
            (
                "Most Network-Active Activities (Bytes Moved)",
                [name for name, _ in network_top],
                [value for _, value in network_top],
                "Bytes",
            )
        )

    gpu_top = sorted(gpu_by_activity.items(), key=lambda row: row[1], reverse=True)[:5]
    if gpu_top:
        charts.append(
            (
                "Highest GPU Memory Delta Activities",
                [name for name, _ in gpu_top],
                [value for _, value in gpu_top],
                "Bytes",
            )
        )

    return charts


def _build_ml_learning_plot_spec(dataset: Dict[str, Any]) -> Dict[str, Any] | None:
    """Build a learning trend line-plot specification for ml_workflow reports."""
    workflow = dataset.get("workflow", {}) if isinstance(dataset.get("workflow"), dict) else {}
    if _to_str(workflow.get("subtype"), "") != ML_Types.WORKFLOW:
        return None

    tasks = dataset.get("tasks", []) if isinstance(dataset.get("tasks"), list) else []
    learning_tasks = [task for task in tasks if _to_str(task.get("subtype"), "") == ML_Types.LEARNING]
    if len(learning_tasks) <= 2:
        return None

    candidate_metrics = ["val_loss", "loss", "best_val_loss", "val_accuracy", "accuracy"]
    selected_metric = None
    points: List[Tuple[float, float]] = []

    for metric in candidate_metrics:
        collected: List[Tuple[float, float]] = []
        for task in learning_tasks:
            ended_at = as_float(task.get("ended_at"))
            generated = task.get("generated", {}) if isinstance(task.get("generated"), dict) else {}
            metric_value = as_float(generated.get(metric))
            if ended_at is not None and metric_value is not None:
                collected.append((ended_at, metric_value))
        if len(collected) > 2:
            selected_metric = metric
            points = sorted(collected, key=lambda item: item[0])
            break

    if selected_metric is None or not points:
        return None

    y_values = [value for _, value in points]
    optimize = "min" if "loss" in selected_metric else "max"
    best_idx = y_values.index(min(y_values) if optimize == "min" else max(y_values))

    return {
        "title": f"Learning Trend Over Time ({selected_metric})",
        "x_ts": [ts for ts, _ in points],
        "y_vals": y_values,
        "y_label": selected_metric,
        "best_idx": best_idx,
    }


def _render_bar_plot(title: str, labels: List[str], values: List[float], y_label: str, output_path: Path) -> None:
    """Render a bar plot image for the PDF plots section."""
    import matplotlib.pyplot as plt

    fig, axis = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("white")
    axis.set_facecolor("#f8fafc")

    wrapped_labels = [
        "\n".join(textwrap.wrap(label, width=14, break_long_words=True, break_on_hyphens=True)) for label in labels
    ]
    bars = axis.bar(wrapped_labels, values, color="#0ea5e9", edgecolor="#0369a1", linewidth=1.0)

    axis.set_title(title, fontsize=13, fontweight="bold", color="#0f172a")
    axis.set_ylabel(y_label, fontsize=10, color="#334155")
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    axis.tick_params(axis="x", labelsize=8)
    axis.tick_params(axis="y", labelsize=9)

    is_bytes = y_label.lower() in {"bytes", "io bytes"}
    is_percent = y_label == "%"
    for bar, value in zip(bars, values):
        if is_bytes:
            label = _fmt_bytes(value)
        elif is_percent:
            label = _fmt_percent(value)
        else:
            label = f"{value:.2f}"
        axis.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            label,
            ha="center",
            va="bottom",
            fontsize=8,
            color="#0f172a",
        )

    fig.tight_layout()
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def _render_ml_line_plot(spec: Dict[str, Any], output_path: Path) -> None:
    """Render line plot for ML learning trend with optimum red marker."""
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    x_datetimes = [datetime.fromtimestamp(ts, tz=timezone.utc) for ts in spec.get("x_ts", [])]
    y_values = spec.get("y_vals", [])
    if not x_datetimes or not y_values:
        return

    fig, axis = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor("white")
    axis.set_facecolor("#f8fafc")

    axis.plot(x_datetimes, y_values, color="#0ea5e9", marker="o", linewidth=1.8, markersize=4)

    best_idx = int(spec.get("best_idx", 0))
    if 0 <= best_idx < len(x_datetimes):
        axis.plot(
            [x_datetimes[best_idx]],
            [y_values[best_idx]],
            marker="x",
            color="#dc2626",
            markersize=10,
            markeredgewidth=2.2,
            linestyle="None",
        )

    axis.set_title(_to_str(spec.get("title"), "Learning Trend"), fontsize=13, fontweight="bold", color="#0f172a")
    axis.set_ylabel(_to_str(spec.get("y_label"), "metric"), fontsize=10, color="#334155")
    axis.grid(axis="y", linestyle="--", alpha=0.35)
    axis.tick_params(axis="x", labelrotation=25, labelsize=8)
    axis.tick_params(axis="y", labelsize=9)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d %H:%M"))
    axis.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=6))

    fig.tight_layout()
    fig.savefig(output_path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def _build_table(rows: List[List[Any]], col_widths: List[float], styles: Dict[str, Any], font_size: int = 8):
    """Build a wrapped ReportLab table with consistent style."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle

    header_style = ParagraphStyle(
        "tbl_header",
        parent=styles["body"],
        fontName="Helvetica-Bold",
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.white,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "tbl_body",
        parent=styles["body"],
        fontName="Helvetica",
        fontSize=font_size,
        leading=font_size + 2,
        textColor=colors.HexColor("#111827"),
        wordWrap="CJK",
    )

    table_rows: List[List[Any]] = []
    for row_index, row in enumerate(rows):
        row_style = header_style if row_index == 0 else body_style
        cells: List[Any] = []
        for cell in row:
            text = _insert_breaks_for_long_tokens(str(cell).strip())
            cells.append(Paragraph(_render_inline(text), row_style))
        table_rows.append(cells)

    table = Table(table_rows, colWidths=col_widths)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
            ]
        )
    )
    return table


def _add_bullet(story: List[Any], text: str, style: Any) -> None:
    """Append one bullet paragraph to story."""
    from reportlab.platypus import Paragraph

    story.append(Paragraph(f"• {_render_inline(text)}", style))


def _build_pdf_document(
    dataset: Dict[str, Any],
    activities: List[Dict[str, Any]],
    object_summary: Dict[str, Any],
    workflow_structure_plot_paths: List[Path],
    plot_paths: List[Path],
    output_path: Path,
) -> None:
    """Build the full PDF report from structured report data."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Image, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer

    workflow = dataset.get("workflow", {}) if isinstance(dataset.get("workflow"), dict) else {}
    tasks = dataset.get("tasks", []) if isinstance(dataset.get("tasks"), list) else []
    objects = dataset.get("objects") or []
    workflow_name_raw = _to_str(workflow.get("name")).strip()
    workflow_id_label = _to_str(workflow.get("workflow_id"))
    workflow_title = workflow_name_raw
    if not workflow_title or workflow_title == "unknown":
        workflow_title = "Workflow"

    start, end, total_elapsed = workflow_bounds(tasks)
    telemetry = _extract_telemetry_overview(tasks)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=LETTER,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36,
        title=f"{workflow_title} - Workflow Provenance Report",
    )

    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Heading1"], fontSize=18, textColor=colors.HexColor("#0f172a"), spaceAfter=2
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"], fontSize=10, textColor=colors.HexColor("#334155"), spaceAfter=6
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontSize=13,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=6,
            spaceAfter=3,
        ),
        "h3": ParagraphStyle(
            "h3",
            parent=base["Heading3"],
            fontSize=11,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=4,
            spaceAfter=2,
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"], fontSize=9, leading=12, textColor=colors.HexColor("#111827")
        ),
        "b1": ParagraphStyle("b1", parent=base["Normal"], fontSize=9, leading=12, leftIndent=10, bulletIndent=0),
        "b2": ParagraphStyle("b2", parent=base["Normal"], fontSize=9, leading=12, leftIndent=24, bulletIndent=12),
        "b3": ParagraphStyle("b3", parent=base["Normal"], fontSize=9, leading=12, leftIndent=38, bulletIndent=24),
        "obj_detail": ParagraphStyle(
            "obj_detail", parent=base["Normal"], fontSize=9, leading=12, leftIndent=52, bulletIndent=0
        ),
        "mono": ParagraphStyle(
            "mono",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=9,
            textColor=colors.HexColor("#111827"),
        ),
        "mono_indent": ParagraphStyle(
            "mono_indent",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.5,
            leading=9,
            leftIndent=52,
            textColor=colors.HexColor("#111827"),
        ),
    }

    story: List[Any] = []

    story.append(Paragraph(workflow_title, styles["title"]))
    story.append(Paragraph("Workflow Provenance Report", styles["subtitle"]))

    # Summary
    story.append(Paragraph("Summary", styles["h2"]))
    code_repo = workflow.get("code_repository", {}) if isinstance(workflow.get("code_repository"), dict) else {}

    _add_summary_bullet(story, "Workflow Name", workflow_name_raw, styles["b1"])
    _add_summary_bullet(story, "Workflow ID", workflow_id_label, styles["b1"])
    _add_summary_bullet(story, "Campaign ID", _to_str(workflow.get("campaign_id")), styles["b1"])
    _add_summary_bullet(story, "Execution Start (UTC)", fmt_timestamp_utc(start), styles["b1"])
    _add_summary_bullet(story, "Execution End (UTC)", fmt_timestamp_utc(end), styles["b1"])
    _add_summary_bullet(story, "Total Elapsed (s)", _fmt_seconds(total_elapsed), styles["b1"])
    _add_summary_bullet(story, "User", _to_str(workflow.get("user")), styles["b1"])
    _add_summary_bullet(story, "System Name", _to_str(workflow.get("sys_name")), styles["b1"])
    _add_summary_bullet(story, "Environment ID", _to_str(workflow.get("environment_id")), styles["b1"])
    if workflow.get("subtype") is not None:
        _add_summary_bullet(story, "Workflow Subtype", _to_str(workflow.get("subtype")), styles["b1"])
    code_repo_text = (
        f"branch={_to_str(code_repo.get('branch'))}, "
        f"short_sha={_to_str(code_repo.get('short_sha'))}, "
        f"dirty={_to_str(code_repo.get('dirty'))}"
    )
    if not (
        _is_empty(_to_str(code_repo.get("branch")))
        and _is_empty(_to_str(code_repo.get("short_sha")))
        and _is_empty(_to_str(code_repo.get("dirty")))
    ):
        _add_bullet(story, f"**Code Repository:** `{code_repo_text}`", styles["b1"])
    _add_summary_bullet(story, "Git Remote", _to_str(code_repo.get("remote")), styles["b1"])

    for section_label, section_key in [
        ("Workflow Used", "used"),
        ("Workflow Generated", "generated"),
        ("Workflow Custom Metadata", "custom_metadata"),
    ]:
        section_data = workflow.get(section_key)
        if not isinstance(section_data, dict) or not section_data:
            continue
        _add_bullet(story, f"**{section_label}:**", styles["b1"])
        for key in sorted(section_data.keys()):
            value = section_data[key]
            if isinstance(value, (dict, list)) and value:
                _add_bullet(story, f"`{key}`:", styles["b2"])
                story.append(Preformatted("\n".join(_format_yaml_like_lines(value)), styles["mono_indent"]))
            else:
                _add_bullet(story, f"`{key}`: `{_safe_repr(value)}`", styles["b2"])

    # Workflow-level summary
    story.append(Paragraph("Workflow-level Summary", styles["h2"]))
    _add_bullet(story, f"**Total Activities:** `{len(activities)}`", styles["b1"])
    _add_bullet(story, f"**Status Counts:** `{_status_counts(tasks)}`", styles["b1"])
    _add_bullet(story, f"**Total Elapsed Workflow Time (s):** `{_fmt_seconds(total_elapsed)}`", styles["b1"])

    slowest = sorted(
        [(_to_str(a.get("activity_id")), as_float(a.get("elapsed_median"))) for a in activities],
        key=lambda item: item[1] if item[1] is not None else -1,
        reverse=True,
    )
    for name, elapsed in slowest[:5]:
        if elapsed is not None:
            _add_bullet(story, f"`{name}`: `{_fmt_seconds(elapsed)} s`", styles["b2"])

    if telemetry.get("samples", 0) > 0:
        resource_items: List[Tuple[str, str]] = []
        memory_text = _fmt_bytes(telemetry.get("memory_used"))
        cpu_text = _fmt_percent(telemetry.get("cpu_percent_avg"))
        read_text = _fmt_bytes(telemetry.get("read_bytes"))
        write_text = _fmt_bytes(telemetry.get("write_bytes"))
        read_ops_text = _fmt_count(telemetry.get("read_count"))
        write_ops_text = _fmt_count(telemetry.get("write_count"))
        if not _is_empty(memory_text):
            resource_items.append(("b2", f"`Memory Used`: `{memory_text}`"))
        if not _is_empty(cpu_text):
            resource_items.append(("b2", f"`Average CPU (%)`: `{cpu_text}`"))
        io_items: List[str] = []
        if not _is_empty(read_text):
            io_items.append(f"`Read`: `{read_text}`")
        if not _is_empty(write_text):
            io_items.append(f"`Write`: `{write_text}`")
        if not _is_empty(read_ops_text):
            io_items.append(f"`Read Ops`: `{read_ops_text}`")
        if not _is_empty(write_ops_text):
            io_items.append(f"`Write Ops`: `{write_ops_text}`")
        if io_items:
            resource_items.append(("b2", "**IO:**"))
            resource_items.extend([("b3", item) for item in io_items])
        if resource_items:
            _add_bullet(story, "**Resource Totals:**", styles["b1"])
            for level, item in resource_items:
                _add_bullet(story, item, styles[level])

    observations: List[str] = []
    if slowest and slowest[0][1] is not None:
        observations.append(f"Slowest Activity: `{slowest[0][0]}` at `{_fmt_seconds(slowest[0][1])} s`")

    io_rank = sorted(
        [(_to_str(task.get("activity_id")), _extract_io_bytes(task)) for task in tasks],
        key=lambda row: row[1],
        reverse=True,
    )
    if io_rank and io_rank[0][1] > 0:
        top_name = io_rank[0][0]
        top_task = next((task for task in tasks if _to_str(task.get("activity_id")) == top_name), None)
        if top_task is not None:
            start = (
                top_task.get("telemetry_at_start", {}) if isinstance(top_task.get("telemetry_at_start"), dict) else {}
            )
            end = top_task.get("telemetry_at_end", {}) if isinstance(top_task.get("telemetry_at_end"), dict) else {}
            read_b = _positive(
                _delta(
                    _deep_get(start, ["disk", "io_sum", "read_bytes"]), _deep_get(end, ["disk", "io_sum", "read_bytes"])
                )
            )
            write_b = _positive(
                _delta(
                    _deep_get(start, ["disk", "io_sum", "write_bytes"]),
                    _deep_get(end, ["disk", "io_sum", "write_bytes"]),
                )
            )
            read_label = _fmt_bytes(read_b)
            write_label = _fmt_bytes(write_b)
            if not (_is_empty(read_label) and _is_empty(write_label)):
                observations.append(
                    f"Largest IO Activity: `{top_name}` with Read `{read_label}` and Write `{write_label}`"
                )
    if observations:
        _add_bullet(story, "**Key Observations:**", styles["b1"])
        for line in observations:
            _add_bullet(story, line, styles["b2"])

    # Workflow structure
    story.append(Paragraph("Workflow Structure", styles["h2"]))
    available_structure_plots = [p for p in workflow_structure_plot_paths if p.exists()]
    if available_structure_plots:
        for idx, structure_plot_path in enumerate(available_structure_plots):
            if idx > 0:
                story.append(Paragraph(f"Part {idx + 1}", styles["body"]))
            story.append(Image(str(structure_plot_path), width=6.8 * inch, height=1.6 * inch))
            story.append(Spacer(1, 4))
    else:
        story.append(Preformatted(_workflow_structure_text(activities), styles["mono"]))

    # Timing report
    story.append(Paragraph("Timing Report", styles["h2"]))
    story.append(Paragraph("Rows are sorted by First Started At (ascending).", styles["body"]))
    story.append(
        _build_table(
            _timing_rows(activities),
            [1.4 * inch, 1.25 * inch, 1.35 * inch, 1.35 * inch, 1.0 * inch],
            styles,
            font_size=8,
        )
    )
    story.append(Paragraph("Interpretation & Insights", styles["h3"]))
    for line in _timing_insights(activities):
        _add_bullet(story, line, styles["b1"])

    # Per activity details
    story.append(Paragraph("Per Activity Details", styles["h2"]))
    grouped = _group_by_activity(tasks)
    ordered_activity_ids = [_to_str(activity.get("activity_id")) for activity in activities]
    for activity_id in ordered_activity_ids:
        lines = _activity_detail_lines(grouped.get(activity_id, []), activity_id)
        for idx, line in enumerate(lines):
            if idx == 0:
                _add_bullet(story, line, styles["b1"])
            elif line in {"Used:", "Generated:", "Used (aggregated):", "Generated (aggregated):"}:
                _add_bullet(story, line, styles["b2"])
            else:
                _add_bullet(story, line, styles["b3"])

    detail_insights = _activity_detail_insights(tasks)
    if detail_insights:
        story.append(Paragraph("Interpretation & Insights", styles["h3"]))
        for line in detail_insights:
            _add_bullet(story, line, styles["b1"])

    # Workflow-level resource usage
    workflow_resource_rows = [["Metric", "Value"]]
    workflow_metrics = [
        ("Telemetry Samples (task start/end pairs)", _fmt_count(telemetry.get("samples"))),
        ("CPU User Time Delta", _fmt_seconds(telemetry.get("cpu_user"))),
        ("CPU System Time Delta", _fmt_seconds(telemetry.get("cpu_system"))),
        ("Average CPU (%) Delta", _fmt_percent(telemetry.get("cpu_percent_avg"))),
        ("Average CPU Frequency", _fmt_count(telemetry.get("cpu_frequency_avg"))),
        ("Memory Used Delta", _fmt_bytes(telemetry.get("memory_used"))),
        ("Average Memory (%)", _fmt_percent(telemetry.get("memory_percent_avg"))),
        ("Average Swap (%)", _fmt_percent(telemetry.get("swap_percent_avg"))),
        ("Disk Read Time Delta (ms)", _fmt_seconds(telemetry.get("disk_read_time"))),
        ("Disk Write Time Delta (ms)", _fmt_seconds(telemetry.get("disk_write_time"))),
        ("Disk Busy Time Delta (ms)", _fmt_seconds(telemetry.get("disk_busy_time"))),
    ]
    for key, value in workflow_metrics:
        if not _is_empty(value):
            workflow_resource_rows.append([key, value])
    workflow_insight_lines: List[str] = []
    if not _is_empty(_fmt_percent(telemetry.get("cpu_percent_avg"))):
        workflow_insight_lines.append(
            f"CPU-heavy period (avg delta): `{_fmt_percent(telemetry.get('cpu_percent_avg'))}`."
        )
    if not _is_empty(_fmt_bytes(telemetry.get("memory_used"))):
        workflow_insight_lines.append(f"Memory pressure (delta): `{_fmt_bytes(telemetry.get('memory_used'))}`.")
    if not _is_empty(_fmt_bytes(telemetry.get("read_bytes"))) or not _is_empty(
        _fmt_bytes(telemetry.get("write_bytes"))
    ):
        workflow_insight_lines.append(
            f"Disk IO pressure: read `{_fmt_bytes(telemetry.get('read_bytes'))}`, "
            f"write `{_fmt_bytes(telemetry.get('write_bytes'))}`."
        )
    if len(workflow_resource_rows) > 1 or workflow_insight_lines:
        story.append(Paragraph("Workflow-level Resource Usage", styles["h2"]))
        if len(workflow_resource_rows) > 1:
            story.append(_build_table(workflow_resource_rows, [2.8 * inch, 3.8 * inch], styles, font_size=9))
        if workflow_insight_lines:
            story.append(Paragraph("Interpretation & Insights", styles["h3"]))
            for line in workflow_insight_lines:
                _add_bullet(story, line, styles["b1"])

    # Per-activity resource usage
    per_activity_rows = _resource_rows(tasks)
    per_activity_has_useful = any(any(not _is_empty(value) for value in row[2:]) for row in per_activity_rows[1:])
    resource_lines = _resource_insights(tasks)
    if per_activity_has_useful or resource_lines:
        story.append(Paragraph("Per-activity Resource Usage", styles["h2"]))
        if per_activity_has_useful:
            story.append(
                _build_table(
                    per_activity_rows,
                    [
                        1.2 * inch,
                        0.7 * inch,
                        0.7 * inch,
                        0.8 * inch,
                        0.6 * inch,
                        0.8 * inch,
                        0.8 * inch,
                        0.7 * inch,
                        0.7 * inch,
                        0.7 * inch,
                    ],
                    styles,
                    font_size=7,
                )
            )
        if resource_lines:
            story.append(Paragraph("Interpretation & Insights", styles["h3"]))
            for line in resource_lines:
                if line.endswith(":"):
                    _add_bullet(story, line, styles["b1"])
                else:
                    _add_bullet(story, line, styles["b2"])

    # Object artifacts summary
    if int(object_summary.get("total_objects", 0) or 0) > 0:
        story.append(Paragraph("Object Artifacts Summary", styles["h2"]))
        object_rows = [["Metric", "Value"]]
        object_rows.extend(
            [
                ["Total Objects", _to_str(object_summary.get("total_objects"), "0")],
                ["By Type", _to_str(object_summary.get("by_type"), "{}")],
                ["By Storage", _to_str(object_summary.get("by_storage"), "{}")],
                ["Task-linked Objects", _to_str(object_summary.get("task_linked"), "0")],
                ["Workflow-linked Objects", _to_str(object_summary.get("workflow_linked"), "0")],
                ["Max Version", _to_str(object_summary.get("max_version"), "-")],
                ["Total Size", _fmt_bytes(as_float(object_summary.get("total_size_bytes")))],
                ["Average Size", _fmt_bytes(as_float(object_summary.get("avg_size_bytes")))],
                ["Max Size", _fmt_bytes(as_float(object_summary.get("max_size_bytes")))],
            ]
        )
        story.append(_build_table(object_rows, [2.8 * inch, 3.8 * inch], styles, font_size=9))

        story.append(Paragraph("Object Details by Type", styles["h3"]))
        grouped_objects: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for obj in objects:
            grouped_objects[_to_str(obj.get("type"), "unknown")].append(obj)

        for obj_type in sorted(grouped_objects.keys()):
            story.append(Paragraph(f"• <b>{html.escape(_object_type_label(obj_type))}</b>:", styles["b1"]))
            ranked = sorted(
                grouped_objects[obj_type],
                key=lambda obj: (
                    as_float(obj.get("updated_at")) if as_float(obj.get("updated_at")) is not None else float("-inf"),
                    as_float(obj.get("version")) if as_float(obj.get("version")) is not None else float("-inf"),
                ),
                reverse=True,
            )
            for obj in ranked[:5]:
                object_id = _to_str(obj.get("object_id"), "-")
                version = _to_str(obj.get("version"), "-")
                storage = _to_str(obj.get("storage_type"), "-")
                size = _fmt_bytes(as_float(obj.get("object_size_bytes")))
                _add_bullet(
                    story,
                    f"`{object_id}` (version=`{version}`, storage=`{storage}`, size=`{size}`)",
                    styles["b2"],
                )

                story.append(
                    Paragraph(_render_inline(f"`task_id`: `{_to_str(obj.get('task_id'), '-')}`"), styles["obj_detail"])
                )
                story.append(
                    Paragraph(
                        _render_inline(f"`workflow_id`: `{_to_str(obj.get('workflow_id'), '-')}`"), styles["obj_detail"]
                    )
                )
                story.append(
                    Paragraph(
                        _render_inline(f"`timestamp`: `{_object_timestamp(obj)}`"),
                        styles["obj_detail"],
                    )
                )
                story.append(
                    Paragraph(
                        _render_inline(f"`sha256`: `{_to_str(obj.get('data_sha256'), '-')}`"),
                        styles["obj_detail"],
                    )
                )
                tags = obj.get("tags")
                if isinstance(tags, list) and tags:
                    story.append(
                        Paragraph(
                            _render_inline(f"`tags`: `{', '.join(str(tag) for tag in tags)}`"),
                            styles["obj_detail"],
                        )
                    )
                story.append(Paragraph(_render_inline("`custom_metadata`:"), styles["obj_detail"]))
                metadata = obj.get("custom_metadata", {})
                story.append(Preformatted("\n".join(_format_yaml_like_lines(metadata)), styles["mono_indent"]))
                story.append(Spacer(1, 12))

    # Aggregation method
    has_aggregated_activity = any(int(activity.get("n_tasks", 0) or 0) > 1 for activity in activities)
    if has_aggregated_activity:
        story.append(Paragraph("Aggregation Method", styles["h2"]))
        _add_bullet(story, "Grouping key: `activity_id`.", styles["b1"])
        _add_bullet(story, "Each grouped row may aggregate multiple task records (`n_tasks`).", styles["b1"])
        _add_bullet(story, "Aggregated metrics currently include count/status/timing.", styles["b1"])

    # Generator line (must be the final content of the PDF).
    generated_at = datetime.now().astimezone().strftime("%b %d, %Y at %I:%M %p %Z")
    footer_text = (
        "Provenance report generated by [Flowcept](https://flowcept.org/) | "
        "[GitHub](https://github.com/ORNL/flowcept) | "
        f"[Version: {__version__}]"
        f"(https://github.com/ORNL/flowcept/releases/tag/v{__version__}) on {generated_at}"
    )

    # Plots (last section)
    if plot_paths:
        story.append(PageBreak())
        story.append(Paragraph("Plots", styles["h2"]))
        for path in plot_paths:
            story.append(Image(str(path), width=6.8 * inch, height=2.7 * inch))
            story.append(Spacer(1, 10))

    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            _render_inline(footer_text),
            styles["body"],
        )
    )

    doc.build(story)


def render_provenance_report_pdf(
    dataset: Dict[str, Any],
    activities: List[Dict[str, Any]],
    object_summary: Dict[str, Any],
    output_path: Path,
) -> Dict[str, Any]:
    """Render a provenance-report PDF from structured report data.

    Parameters
    ----------
    dataset : dict
        Structured report dataset with workflow/tasks/objects records.
    activities : list of dict
        Aggregated activity rows.
    object_summary : dict
        Summary counts/size statistics for object artifacts.
    output_path : pathlib.Path
        Destination PDF file path.

    Returns
    -------
    dict
        Render metadata with output path and plot count.
    """
    # Optional deps are imported here so markdown-only users don't require PDF stack.
    try:
        import matplotlib
        import reportlab  # noqa: F401
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PDF report generation requires optional dependencies. Install with: pip install flowcept[report_pdf]"
        ) from exc

    matplotlib.use("Agg", force=True)

    tasks = dataset.get("tasks", []) if isinstance(dataset.get("tasks"), list) else []
    with TemporaryDirectory(prefix="flowcept_report_pdf_") as temp_dir:
        tmp = Path(temp_dir)
        plot_paths: List[Path] = []
        workflow_structure_plot_paths: List[Path] = []

        try:
            workflow_structure_plot_paths = _render_workflow_structure_plots(activities=activities, output_dir=tmp)
        except Exception:
            workflow_structure_plot_paths = []

        ml_plot_spec = _build_ml_learning_plot_spec(dataset)
        if ml_plot_spec is not None:
            ml_plot_path = tmp / "plot_1_ml_line.png"
            _render_ml_line_plot(ml_plot_spec, ml_plot_path)
            plot_paths.append(ml_plot_path)

        plots = _build_plot_data(activities=activities, tasks=tasks)
        for idx, (title, labels, values, y_label) in enumerate(plots):
            plot_index = idx + 2 if ml_plot_spec is not None else idx + 1
            plot_path = tmp / f"plot_{plot_index}.png"
            _render_bar_plot(title=title, labels=labels, values=values, y_label=y_label, output_path=plot_path)
            plot_paths.append(plot_path)

        _build_pdf_document(
            dataset=dataset,
            activities=activities,
            object_summary=object_summary,
            workflow_structure_plot_paths=workflow_structure_plot_paths,
            plot_paths=plot_paths,
            output_path=output_path,
        )

    return {"output": str(output_path), "plots": len(plot_paths)}
