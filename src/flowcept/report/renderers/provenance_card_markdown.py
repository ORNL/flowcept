"""Markdown renderer for provenance-card reports."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import math
from pathlib import Path
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from flowcept import __version__
from flowcept.report.aggregations import as_float, elapsed_seconds, fmt_timestamp_utc
from flowcept.report.sanitization import sanitize_json_like


def render_markdown_file_into_rich_terminal(markdown_path: str | Path, *, stream=None) -> None:
    """Render a markdown file into a Rich-enabled terminal stream."""
    stream = stream or sys.stdout
    markdown_path = Path(markdown_path)
    text = markdown_path.read_text(encoding="utf-8", errors="replace")

    from rich.console import Console
    from rich.markdown import Markdown

    console = Console(file=stream, force_terminal=getattr(stream, "isatty", lambda: False)(), soft_wrap=True)
    lines = text.splitlines()
    markdown_buffer: List[str] = []

    def flush_markdown_buffer() -> None:
        if not markdown_buffer:
            return
        console.print(Markdown("\n".join(markdown_buffer), justify="left"))
        markdown_buffer.clear()

    seen_heading = False
    for line in lines:
        match = re.match(r"^(#{1,6})\s+(.*)$", line)
        if match:
            flush_markdown_buffer()
            if seen_heading:
                console.print("")
            title = match.group(2).strip()
            console.print(f"[bold]{title}[/bold]")
            console.print("")
            seen_heading = True
            continue
        markdown_buffer.append(line)

    flush_markdown_buffer()


def _to_str(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default
    return str(value)


def _fmt_seconds(value: Optional[float]) -> str:
    if value is None:
        return "unknown"
    return f"{float(value):.3f}"


def _fmt_percent(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "-"
    return f"{value:.1f}%"


def _fmt_count(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "-"
    return f"{int(value):,}"


def _fmt_bytes(value: Optional[float]) -> str:
    if value is None or value <= 0:
        return "-"
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(value)
    idx = 0
    while v >= 1024 and idx < len(units) - 1:
        v /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(v)} {units[idx]}"
    return f"{v:.2f} {units[idx]}"


def _fmt_text(value: Any, default: str = "-") -> str:
    """Render scalar values with a consistent empty fallback."""
    if value is None:
        return default
    text = str(value)
    return text if text else default


def _fmt_nonzero_seconds(value: Optional[float]) -> str:
    """Render seconds only when strictly positive."""
    if value is None or value <= 0:
        return "-"
    return f"{float(value):.3f}"


def _is_simple_value(value: Any) -> bool:
    """Return True for simple scalar values suitable for summary display."""
    return isinstance(value, (str, int, float, bool))


def _render_table(headers: List[str], rows: List[List[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |" for row in rows] if rows else []
    if not body:
        body = ["| " + " | ".join(["-"] * len(headers)) + " |"]
    return "\n".join([head, sep] + body)


def _is_empty_metric(value: Any) -> bool:
    """Return True when a rendered metric is effectively empty."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() in {"-", "unknown", "", "- / -", "-/-"}
    return False


def _append_summary_line(lines: List[str], label: str, value: Any) -> None:
    """Append summary bullet only when value is meaningful."""
    if _is_empty_metric(value):
        return
    lines.append(f"- **{label}:** `{value}`")


def _filter_all_empty_columns(
    headers: List[str],
    rows: List[List[Any]],
    keep_indices: List[int],
) -> Tuple[List[str], List[List[Any]]]:
    """Drop columns whose values are empty across all rows."""
    if not rows:
        return headers, rows
    keep = set(keep_indices)
    for col_ix in range(len(headers)):
        if col_ix in keep:
            continue
        if any(not _is_empty_metric(row[col_ix]) for row in rows):
            keep.add(col_ix)
    kept = [ix for ix in range(len(headers)) if ix in keep]
    return [headers[ix] for ix in kept], [[row[ix] for ix in kept] for row in rows]


def _flatten_dict(prefix: str, value: Any, out: Dict[str, Any]) -> None:
    """Flatten nested dict values into dotted keys."""
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else str(k)
            _flatten_dict(child, v, out)
        return
    out[prefix] = value


def _safe_sample(value: Any, max_len: int = 80) -> str:
    """Render a compact sanitized example value (single line, no newlines)."""
    safe = sanitize_json_like(value)
    text = " ".join(str(safe).split())  # collapse all whitespace/newlines to single spaces
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _format_json_like(value: Any, max_len: int = 220) -> str:
    """Render a compact JSON-like string for metadata display."""
    safe = sanitize_json_like(value)
    try:
        text = json.dumps(safe, sort_keys=True, default=str)
    except Exception:
        text = str(safe)
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _format_scalar_multiline(value: Any) -> List[str]:
    """Format scalar metadata values, preserving multiline strings."""
    safe = sanitize_json_like(value)
    if isinstance(safe, str):
        if "\n" not in safe:
            return [safe]
        lines = ["|"]
        for row in safe.splitlines():
            lines.append(f"  {row}")
        return lines
    if safe is None:
        return ["null"]
    if isinstance(safe, bool):
        return ["true" if safe else "false"]
    return [str(safe)]


def _format_nested_metadata_lines(value: Any, indent: int = 0) -> List[str]:
    """Render nested metadata using an indented YAML-like representation."""
    safe = sanitize_json_like(value)
    pad = " " * indent

    if isinstance(safe, dict):
        if not safe:
            return [f"{pad}{{}}"]
        lines: List[str] = []
        for key in sorted(safe.keys(), key=str):
            item = safe[key]
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_format_nested_metadata_lines(item, indent=indent + 2))
                continue
            scalar_lines = _format_scalar_multiline(item)
            if len(scalar_lines) == 1:
                lines.append(f"{pad}{key}: {scalar_lines[0]}")
                continue
            lines.append(f"{pad}{key}: {scalar_lines[0]}")
            for row in scalar_lines[1:]:
                lines.append(f"{pad}{row}")
        return lines

    if isinstance(safe, list):
        if not safe:
            return [f"{pad}[]"]
        lines = []
        for item in safe:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_format_nested_metadata_lines(item, indent=indent + 2))
                continue
            scalar_lines = _format_scalar_multiline(item)
            if len(scalar_lines) == 1:
                lines.append(f"{pad}- {scalar_lines[0]}")
                continue
            lines.append(f"{pad}- {scalar_lines[0]}")
            for row in scalar_lines[1:]:
                lines.append(f"{pad}  {row}")
        return lines

    scalar_lines = _format_scalar_multiline(safe)
    return [f"{pad}{row}" for row in scalar_lines]


def _extract_object_timestamp(obj: Dict[str, Any]) -> Optional[float]:
    """Extract best-effort object timestamp from common object record fields."""
    for key in ["updated_at", "utc_timestamp", "timestamp", "ended_at", "started_at", "created_at", "submitted_at"]:
        raw = obj.get(key)
        value = as_float(raw)
        if value is not None:
            return value
        if isinstance(raw, dict):
            value = as_float(raw.get("$date"))
            if value is not None:
                return value
    return None


def _object_type_header_label(obj_type: str) -> str:
    """Return human-friendly object type header labels."""
    normalized = obj_type.lower().strip()
    if normalized in {"ml_model", "model"}:
        return "Models"
    if normalized in {"dataset", "data_set"}:
        return "Datasets"
    return f"{obj_type.replace('_', ' ').title()}s"


def _build_object_details_lines(objects: List[Dict[str, Any]]) -> List[str]:
    """Build markdown lines for up to five latest object entries per type."""
    lines: List[str] = ["### Object Details by Type"]
    if not objects:
        lines.append("- No object records were available.")
        return lines

    grouped: Dict[str, List[Tuple[int, Dict[str, Any]]]] = defaultdict(list)
    for idx, obj in enumerate(objects):
        obj_type = _to_str(obj.get("type"))
        grouped[obj_type].append((idx, obj))

    for obj_type in sorted(grouped.keys()):
        label = _object_type_header_label(obj_type)
        lines.append(f"- **{label}:**")
        ranked = sorted(
            grouped[obj_type],
            key=lambda pair: (
                _extract_object_timestamp(pair[1]) if _extract_object_timestamp(pair[1]) is not None else float("-inf"),
                as_float(pair[1].get("version")) if as_float(pair[1].get("version")) is not None else float("-inf"),
                pair[0],
            ),
            reverse=True,
        )
        for _, obj in ranked[:5]:
            lines.append(
                "  - "
                f"`{_to_str(obj.get('object_id'))}` "
                f"(version=`{_to_str(obj.get('version'), default='-')}`, "
                f"storage=`{_to_str(obj.get('storage_type'), default='-')}`, "
                f"size=`{_fmt_bytes(as_float(obj.get('object_size_bytes')))}" + "`)"
            )
            lines.append(
                "    <br> "
                f"`task_id`: `{_to_str(obj.get('task_id'), default='-')}`; "
                f"`workflow_id`: `{_to_str(obj.get('workflow_id'), default='-')}`; "
                f"`timestamp`: `{fmt_timestamp_utc(_extract_object_timestamp(obj))}`"
            )
            lines.append(f"    <br> `sha256`: `{_to_str(obj.get('data_sha256'), default='-')}`")
            raw_tags = obj.get("tags")
            if isinstance(raw_tags, list) and raw_tags:
                tags_text = ", ".join(str(tag) for tag in raw_tags)
                lines.append(f"    <br> `tags`: `{tags_text}`")
            lines.append("    <br> `custom_metadata`:")
            lines.append("    ```yaml")
            metadata_lines = _format_nested_metadata_lines(obj.get("custom_metadata", {}))
            for row in metadata_lines:
                lines.append(f"    {row}")
            lines.append("    ```")
    return lines


def _percentile(sorted_vals: List[float], pct: float) -> float:
    """Compute percentile from a sorted list using nearest-rank interpolation."""
    if not sorted_vals:
        return math.nan
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * pct
    lo = int(math.floor(idx))
    hi = int(math.ceil(idx))
    if lo == hi:
        return sorted_vals[lo]
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _iqr_bounds(values: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """Return IQR lower/upper bounds for outlier detection."""
    if len(values) < 4:
        return None, None
    sorted_vals = sorted(values)
    q1 = _percentile(sorted_vals, 0.25)
    q3 = _percentile(sorted_vals, 0.75)
    iqr = q3 - q1
    return q1 - 1.5 * iqr, q3 + 1.5 * iqr


def _summarize_field_values(values: List[Any], total_runs: int) -> str:
    """Summarize flattened field values across multiple activity runs."""
    present = len(values)
    presence = f"{(present / total_runs) * 100:.1f}%"

    numeric_vals = [as_float(v) for v in values]
    numeric_vals = [v for v in numeric_vals if v is not None]
    if numeric_vals and len(numeric_vals) == len(values):
        numeric_vals.sort()
        p50 = _percentile(numeric_vals, 0.50)
        p95 = _percentile(numeric_vals, 0.95)
        return (
            f"presence={presence}; type=numeric; min={numeric_vals[0]:.3f}; "
            f"p50={p50:.3f}; p95={p95:.3f}; max={numeric_vals[-1]:.3f}"
        )

    shape_counter: Counter[str] = Counter()
    scalar_counter: Counter[str] = Counter()
    for v in values:
        if isinstance(v, (list, tuple)) and v and all(isinstance(x, int) for x in v):
            shape_counter[str(list(v))] += 1
        elif isinstance(v, (str, int, float, bool)):
            scalar_counter[_safe_sample(v, max_len=40)] += 1

    if shape_counter:
        top = ", ".join(f"{k} (×{c})" if c > 1 else k for k, c in shape_counter.most_common(2))
        return f"presence={presence}; type=shape-like; top_shapes={top}"
    if scalar_counter:
        top = ", ".join(f"{k} (×{c})" if c > 1 else k for k, c in scalar_counter.most_common(3))
        return f"presence={presence}; type=scalar/categorical; top_values={top}"

    return f"presence={presence}; type=mixed; sample={_safe_sample(values[0])}"


def _format_single_field_value(value: Any) -> str:
    """Format a single used/generated field value without aggregation metadata."""
    if isinstance(value, (dict, list, tuple)):
        return _format_json_like(value, max_len=220)
    return _safe_sample(value, max_len=140)


_HOST_DISPLAY_MAX = 10


def _build_activity_io_summary(
    tasks_sorted: List[Dict[str, Any]],
    heading: str = "##",
    include_header: bool = True,
    hostname_data: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Build markdown lines for aggregated used/generated summaries by activity.

    Parameters
    ----------
    tasks_sorted:
        Flat list of task records sorted by start time.
    heading:
        Markdown heading prefix for the section (default ``"##"``).
        Pass ``"####"`` to nest this section inside a deeper heading.
    include_header:
        If True, prepend the ``Per Activity Details`` heading line.
    hostname_data:
        Optional mapping of activity_id → Counter[hostname, task_count].
        When provided, a host distribution block is appended after each
        activity's used/generated summary.
    """
    by_activity: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for task in tasks_sorted:
        by_activity[_to_str(task.get("activity_id"))].append(task)

    lines: List[str] = [f"{heading} Per Activity Details"] if include_header else []
    activity_used_field_counts: List[Tuple[str, int]] = []
    activity_generated_field_counts: List[Tuple[str, int]] = []
    variability_candidates: List[Tuple[str, str, float]] = []
    for activity, members in by_activity.items():
        n_runs = len(members)
        subtype_values = sorted(
            {
                _to_str(member.get("subtype"), default="").strip()
                for member in members
                if _to_str(member.get("subtype"), default="").strip()
            }
        )
        if n_runs == 1:
            if subtype_values:
                subtype_text = ", ".join(f"`{s}`" for s in subtype_values)
                lines.append(f"- **{activity}** (subtype={subtype_text})")
            else:
                lines.append(f"- **{activity}**")
            tags = members[0].get("tags")
            if isinstance(tags, list) and len(tags) > 0:
                if len(tags) == 1:
                    lines.append(f"  - Tag: `{_safe_sample(tags[0], max_len=140)}`")
                else:
                    tags_text = ", ".join(f"`{_safe_sample(tag, max_len=140)}`" for tag in tags)
                    lines.append(f"  - Tags: {tags_text}")
        else:
            if subtype_values:
                subtype_text = ", ".join(f"`{s}`" for s in subtype_values)
                lines.append(f"- **{activity}** (`n={n_runs}`, subtype={subtype_text})")
            else:
                lines.append(f"- **{activity}** (`n={n_runs}`)")

        used_fields: Dict[str, List[Any]] = defaultdict(list)
        gen_fields: Dict[str, List[Any]] = defaultdict(list)
        for task in members:
            used = task.get("used", {})
            generated = task.get("generated", {})
            if isinstance(used, dict):
                flat: Dict[str, Any] = {}
                _flatten_dict("", used, flat)
                for k, v in flat.items():
                    used_fields[k].append(v)
            if isinstance(generated, dict):
                flat = {}
                _flatten_dict("", generated, flat)
                for k, v in flat.items():
                    gen_fields[k].append(v)

        if used_fields:
            lines.append("  - Used:" if n_runs == 1 else "  - Used (aggregated):")
            activity_used_field_counts.append((activity, len(used_fields)))
            for key in sorted(used_fields.keys())[:8]:
                if n_runs == 1:
                    lines.append(f"    - `{key}`: `{_format_single_field_value(used_fields[key][0])}`")
                else:
                    lines.append(f"    - `{key}`: {_summarize_field_values(used_fields[key], n_runs)}")
                numeric_vals = [as_float(v) for v in used_fields[key]]
                numeric_vals = [v for v in numeric_vals if v is not None]
                if numeric_vals and len(numeric_vals) == len(used_fields[key]):
                    variability_candidates.append((activity, f"used.{key}", max(numeric_vals) - min(numeric_vals)))
        if gen_fields:
            lines.append("  - Generated:" if n_runs == 1 else "  - Generated (aggregated):")
            activity_generated_field_counts.append((activity, len(gen_fields)))
            for key in sorted(gen_fields.keys())[:8]:
                if n_runs == 1:
                    lines.append(f"    - `{key}`: `{_format_single_field_value(gen_fields[key][0])}`")
                else:
                    lines.append(f"    - `{key}`: {_summarize_field_values(gen_fields[key], n_runs)}")
                numeric_vals = [as_float(v) for v in gen_fields[key]]
                numeric_vals = [v for v in numeric_vals if v is not None]
                if numeric_vals and len(numeric_vals) == len(gen_fields[key]):
                    variability_candidates.append((activity, f"generated.{key}", max(numeric_vals) - min(numeric_vals)))

        if hostname_data is not None:
            host_counts = hostname_data.get(activity)
            if host_counts:
                sorted_hosts = host_counts.most_common()
                lines.append("  - Hosts (tasks per host):")
                for host, count in sorted_hosts[:_HOST_DISPLAY_MAX]:
                    lines.append(f"    - `{host}`: {count} task(s)")
                if len(sorted_hosts) > _HOST_DISPLAY_MAX:
                    remaining = len(sorted_hosts) - _HOST_DISPLAY_MAX
                    lines.append(f"    - _...and {remaining} other host(s) also executed tasks in this activity_")
    lines.append("")
    insight_lines: List[str] = []
    if activity_used_field_counts:
        top_used = sorted(activity_used_field_counts, key=lambda x: x[1], reverse=True)[:3]
        insight_lines.append(
            "- Activities with richest **used** metadata: " + ", ".join(f"`{a}` ({n} fields)" for a, n in top_used)
        )
    if activity_generated_field_counts:
        top_gen = sorted(activity_generated_field_counts, key=lambda x: x[1], reverse=True)[:3]
        insight_lines.append(
            "- Activities with richest **generated** metadata: " + ", ".join(f"`{a}` ({n} fields)" for a, n in top_gen)
        )
    if variability_candidates:
        top_var = sorted(variability_candidates, key=lambda x: x[2], reverse=True)[:5]
        insight_lines.append(
            "- Highest numeric variability fields: " + ", ".join(f"`{a}:{f}` (range={v:.3f})" for a, f, v in top_var)
        )
    if insight_lines:
        lines.append(f"{heading}# Interpretation & Insights")
        lines.extend(insight_lines)
    lines.append("")
    return lines


def _build_per_activity_resource_section(
    tasks_sorted: List[Dict[str, Any]],
    heading: str = "##",
) -> List[str]:
    """Build markdown lines for the per-activity resource usage section.

    Returns an empty list when no telemetry data is present.

    Parameters
    ----------
    tasks_sorted:
        Flat list of task records (sorted by start time is preferred but not required).
    heading:
        Markdown heading prefix for the section (default ``"##"``).
        Pass ``"####"`` to nest this section inside a deeper heading.
    """
    telemetry_available = any(
        isinstance(t.get("telemetry_at_start"), dict) and isinstance(t.get("telemetry_at_end"), dict)
        for t in tasks_sorted
    )
    if not telemetry_available:
        return []

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
    activity_process_cpu: Dict[str, float] = defaultdict(float)
    activity_net_sent: Dict[str, float] = defaultdict(float)
    activity_net_recv: Dict[str, float] = defaultdict(float)
    activity_gpu: Dict[str, float] = defaultdict(float)

    for task in tasks_sorted:
        activity = _to_str(task.get("activity_id"))
        if activity not in activity_order:
            activity_order.append(activity)
        start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
        end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
        delta = _compute_telemetry_delta(start, end)
        elapsed_value = elapsed_seconds(task.get("started_at"), task.get("ended_at"))
        if elapsed_value is not None:
            activity_elapsed[activity].append(elapsed_value)
        activity_cpu_user[activity] += delta["cpu_user"] or 0.0
        activity_cpu_system[activity] += delta["cpu_system"] or 0.0
        activity_memory[activity] += delta["memory_used"] or 0.0
        activity_read[activity] += delta["read_bytes"] or 0.0
        activity_write[activity] += delta["write_bytes"] or 0.0
        activity_read_ops[activity] += delta["read_count"] or 0.0
        activity_write_ops[activity] += delta["write_count"] or 0.0
        if delta["cpu_percent"] is not None:
            activity_cpu_percent[activity].append(delta["cpu_percent"])
        process_cpu = (
            _delta(
                _deep_get(start, ["process", "cpu_percent"]),
                _deep_get(end, ["process", "cpu_percent"]),
            )
            or 0.0
        )
        activity_process_cpu[activity] += process_cpu
        net_sent = (
            _delta(
                _deep_get(start, ["network", "netio_sum", "bytes_sent"]),
                _deep_get(end, ["network", "netio_sum", "bytes_sent"]),
            )
            or 0.0
        )
        net_recv = (
            _delta(
                _deep_get(start, ["network", "netio_sum", "bytes_recv"]),
                _deep_get(end, ["network", "netio_sum", "bytes_recv"]),
            )
            or 0.0
        )
        activity_net_sent[activity] += net_sent
        activity_net_recv[activity] += net_recv
        task_gpu_delta = 0.0
        start_gpu = start.get("gpu", {}) if isinstance(start.get("gpu"), dict) else {}
        end_gpu = end.get("gpu", {}) if isinstance(end.get("gpu"), dict) else {}
        for gpu_key, gpu_end_val in end_gpu.items():
            if not isinstance(gpu_end_val, dict):
                continue
            flat_end: Dict[str, float] = {}
            _flatten_numeric("", gpu_end_val, flat_end)
            flat_start: Dict[str, float] = {}
            gpu_start = start_gpu.get(gpu_key, {}) if isinstance(start_gpu.get(gpu_key), dict) else {}
            _flatten_numeric("", gpu_start, flat_start)
            for metric, v_end in flat_end.items():
                if "used" not in metric.lower() or "gpu" in metric.lower():
                    continue
                v_start = flat_start.get(metric)
                if v_start is not None and v_end >= v_start:
                    task_gpu_delta += v_end - v_start
                else:
                    task_gpu_delta += v_end
        activity_gpu[activity] += task_gpu_delta

    resource_rows: List[List[Any]] = []
    for activity in activity_order:
        elapsed_values = sorted(activity_elapsed.get(activity, []))
        elapsed_median = _percentile(elapsed_values, 0.50) if elapsed_values else None
        cpu_percent_values = activity_cpu_percent.get(activity, [])
        cpu_percent_avg = (sum(cpu_percent_values) / len(cpu_percent_values)) if cpu_percent_values else None
        resource_rows.append(
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

    io_heavy = sorted(
        [(a, activity_read.get(a, 0.0), activity_write.get(a, 0.0)) for a in activity_order],
        key=lambda x: x[1] + x[2],
        reverse=True,
    )
    cpu_heavy = sorted(
        [
            (
                a,
                (sum(activity_cpu_percent.get(a, [])) / len(activity_cpu_percent.get(a, [])))
                if activity_cpu_percent.get(a)
                else 0.0,
            )
            for a in activity_order
        ],
        key=lambda x: x[1],
        reverse=True,
    )
    mem_heavy = sorted(
        [(a, activity_memory.get(a, 0.0)) for a in activity_order],
        key=lambda x: x[1],
        reverse=True,
    )
    process_cpu_heavy = sorted(
        [(a, activity_process_cpu.get(a, 0.0)) for a in activity_order],
        key=lambda x: x[1],
        reverse=True,
    )
    network_heavy = sorted(
        [(a, activity_net_sent.get(a, 0.0), activity_net_recv.get(a, 0.0)) for a in activity_order],
        key=lambda x: x[1] + x[2],
        reverse=True,
    )
    gpu_heavy = sorted(
        [(a, activity_gpu.get(a, 0.0)) for a in activity_order],
        key=lambda x: x[1],
        reverse=True,
    )

    per_activity_headers = [
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
    per_activity_headers, resource_rows = _filter_all_empty_columns(
        per_activity_headers,
        resource_rows,
        keep_indices=[0, 1],
    )
    per_activity_insight_lines: List[str] = []
    if any((read_b + write_b) > 0 for _, read_b, write_b in io_heavy):
        per_activity_insight_lines.append("- Most IO-heavy Activities (Read + Write):")
        for name, read_b, write_b in io_heavy[:5]:
            if read_b + write_b <= 0:
                continue
            per_activity_insight_lines.append(f"  - `{name}`: Read={_fmt_bytes(read_b)}, Write={_fmt_bytes(write_b)}")
    if any(cpu_pct > 0 for _, cpu_pct in cpu_heavy):
        per_activity_insight_lines.append("- Most CPU-active Activities:")
        for name, cpu_pct in cpu_heavy[:5]:
            if cpu_pct <= 0:
                continue
            per_activity_insight_lines.append(f"  - `{name}`: CPU={_fmt_percent(cpu_pct)}")
    if any(mem > 0 for _, mem in mem_heavy):
        per_activity_insight_lines.append("- Largest memory growth Activities:")
        for name, mem in mem_heavy[:5]:
            if mem <= 0:
                continue
            per_activity_insight_lines.append(f"  - `{name}`: Memory Delta={_fmt_bytes(mem)}")
    if any((sent + recv) > 0 for _, sent, recv in network_heavy):
        per_activity_insight_lines.append("- Most network-active Activities:")
        for name, sent, recv in network_heavy[:5]:
            if sent + recv <= 0:
                continue
            per_activity_insight_lines.append(f"  - `{name}`: Sent={_fmt_bytes(sent)}, Received={_fmt_bytes(recv)}")
    if any(proc_cpu > 0 for _, proc_cpu in process_cpu_heavy):
        per_activity_insight_lines.append("- Highest process CPU delta Activities:")
        for name, proc_cpu in process_cpu_heavy[:5]:
            if proc_cpu <= 0:
                continue
            per_activity_insight_lines.append(f"  - `{name}`: Process CPU Delta={_fmt_percent(proc_cpu)}")
    if any(gpu_delta > 0 for _, gpu_delta in gpu_heavy):
        per_activity_insight_lines.append("- Highest GPU memory delta Activities:")
        for name, gpu_delta in gpu_heavy[:5]:
            if gpu_delta <= 0:
                continue
            per_activity_insight_lines.append(f"  - `{name}`: GPU Used Delta={_fmt_bytes(gpu_delta)}")

    per_activity_has_resource_values = any(any(not _is_empty_metric(cell) for cell in row[2:]) for row in resource_rows)
    if not bool(per_activity_has_resource_values or per_activity_insight_lines):
        return []

    lines: List[str] = []
    lines.append(f"{heading} Per-activity Resource Usage")
    if per_activity_has_resource_values:
        lines.append(_render_table(per_activity_headers, resource_rows))
        lines.append("")
    if per_activity_insight_lines:
        lines.append(f"{heading}# Interpretation & Insights")
        lines.extend(per_activity_insight_lines)
        lines.append("")
    return lines


def _deep_get(d: Dict[str, Any], path: List[str]) -> Any:
    cur: Any = d
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _delta(a: Any, b: Any) -> Optional[float]:
    af = as_float(a)
    bf = as_float(b)
    if af is None or bf is None:
        return None
    diff = bf - af
    return diff if diff > 0 else None


def _compute_telemetry_delta(start: Dict[str, Any], end: Dict[str, Any]) -> Dict[str, Any]:
    cpu_start = _deep_get(start, ["cpu"]) or {}
    cpu_end = _deep_get(end, ["cpu"]) or {}
    cpu_times_start = _deep_get(cpu_start, ["times_avg"]) or {}
    cpu_times_end = _deep_get(cpu_end, ["times_avg"]) or {}

    disk_start = _deep_get(start, ["disk"]) or {}
    disk_end = _deep_get(end, ["disk"]) or {}
    io_start = _deep_get(disk_start, ["io_sum"]) or {}
    io_end = _deep_get(disk_end, ["io_sum"]) or {}

    mem_start = _deep_get(start, ["memory", "virtual"]) or {}
    mem_end = _deep_get(end, ["memory", "virtual"]) or {}

    return {
        "cpu_user": _delta(cpu_times_start.get("user"), cpu_times_end.get("user")),
        "cpu_system": _delta(cpu_times_start.get("system"), cpu_times_end.get("system")),
        "cpu_percent": _delta(cpu_start.get("percent_all"), cpu_end.get("percent_all")),
        "memory_used": _delta(mem_start.get("used"), mem_end.get("used")),
        "read_bytes": _delta(io_start.get("read_bytes"), io_end.get("read_bytes")),
        "write_bytes": _delta(io_start.get("write_bytes"), io_end.get("write_bytes")),
        "read_count": _delta(io_start.get("read_count"), io_end.get("read_count")),
        "write_count": _delta(io_start.get("write_count"), io_end.get("write_count")),
    }


def _flatten_numeric(prefix: str, value: Any, out: Dict[str, float]) -> None:
    """Flatten nested dict/list numeric telemetry values into dotted paths."""
    if isinstance(value, dict):
        for k, v in value.items():
            child = f"{prefix}.{k}" if prefix else str(k)
            _flatten_numeric(child, v, out)
        return
    if isinstance(value, list):
        for i, v in enumerate(value):
            child = f"{prefix}[{i}]"
            _flatten_numeric(child, v, out)
        return
    val = as_float(value)
    if val is not None:
        out[prefix] = val


def _extract_telemetry_overview(tasks_sorted: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Aggregate telemetry metrics with graceful fallbacks across all tasks."""
    rows = []
    end_cpu_freq = []
    end_mem_percent = []
    end_swap_percent = []
    end_proc_threads = []
    end_proc_fds = []
    end_proc_open_files = []
    end_proc_conns = []
    end_proc_rss = []
    end_proc_vms = []
    gpu_names = set()
    gpu_ids = set()
    gpu_metric_deltas: Dict[str, float] = defaultdict(float)
    gpu_temp_peaks: Dict[str, float] = {}
    network_end_metrics: Dict[str, float] = defaultdict(float)

    totals = defaultdict(float)

    for task in tasks_sorted:
        start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
        end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
        if not start and not end:
            continue
        rows.append((start, end))
        delta = _compute_telemetry_delta(start, end)
        totals["cpu_user"] += delta["cpu_user"] or 0.0
        totals["cpu_system"] += delta["cpu_system"] or 0.0
        totals["memory_used"] += delta["memory_used"] or 0.0
        totals["read_bytes"] += delta["read_bytes"] or 0.0
        totals["write_bytes"] += delta["write_bytes"] or 0.0
        totals["read_count"] += delta["read_count"] or 0.0
        totals["write_count"] += delta["write_count"] or 0.0
        if delta["cpu_percent"] is not None:
            totals["cpu_percent_sum"] += delta["cpu_percent"]
            totals["cpu_percent_n"] += 1

        end_cpu = end.get("cpu", {}) if isinstance(end.get("cpu"), dict) else {}
        cpu_freq = as_float(end_cpu.get("frequency"))
        if cpu_freq is not None:
            end_cpu_freq.append(cpu_freq)

        end_mem = end.get("memory", {}) if isinstance(end.get("memory"), dict) else {}
        end_virtual = end_mem.get("virtual", {}) if isinstance(end_mem.get("virtual"), dict) else {}
        end_swap = end_mem.get("swap", {}) if isinstance(end_mem.get("swap"), dict) else {}
        vm_percent = as_float(end_virtual.get("percent"))
        if vm_percent is not None:
            end_mem_percent.append(vm_percent)
        sw_percent = as_float(end_swap.get("percent"))
        if sw_percent is not None:
            end_swap_percent.append(sw_percent)
        totals["swap_used"] += (
            _delta(
                _deep_get(start, ["memory", "swap", "used"]),
                _deep_get(end, ["memory", "swap", "used"]),
            )
            or 0.0
        )
        totals["disk_used"] += (
            _delta(
                _deep_get(start, ["disk", "disk_usage", "used"]),
                _deep_get(end, ["disk", "disk_usage", "used"]),
            )
            or 0.0
        )
        totals["disk_percent"] += (
            _delta(
                _deep_get(start, ["disk", "disk_usage", "percent"]),
                _deep_get(end, ["disk", "disk_usage", "percent"]),
            )
            or 0.0
        )

        for key in ["read_time", "write_time", "busy_time"]:
            totals[f"disk_{key}"] += (
                _delta(
                    _deep_get(start, ["disk", "io_sum", key]),
                    _deep_get(end, ["disk", "io_sum", key]),
                )
                or 0.0
            )

        for key in [
            "bytes_sent",
            "bytes_recv",
            "packets_sent",
            "packets_recv",
            "errin",
            "errout",
            "dropin",
            "dropout",
        ]:
            value = _delta(
                _deep_get(start, ["network", "netio_sum", key]),
                _deep_get(end, ["network", "netio_sum", key]),
            )
            if value is not None:
                totals[f"net_{key}"] += value
            end_val = as_float(_deep_get(end, ["network", "netio_sum", key]))
            if end_val is not None:
                network_end_metrics[key] = max(network_end_metrics[key], end_val)

        totals["proc_cpu_user"] += (
            _delta(
                _deep_get(start, ["process", "cpu_times", "user"]),
                _deep_get(end, ["process", "cpu_times", "user"]),
            )
            or 0.0
        )
        totals["proc_cpu_system"] += (
            _delta(
                _deep_get(start, ["process", "cpu_times", "system"]),
                _deep_get(end, ["process", "cpu_times", "system"]),
            )
            or 0.0
        )
        totals["proc_read_bytes"] += (
            _delta(
                _deep_get(start, ["process", "io_counters", "read_bytes"]),
                _deep_get(end, ["process", "io_counters", "read_bytes"]),
            )
            or 0.0
        )
        totals["proc_write_bytes"] += (
            _delta(
                _deep_get(start, ["process", "io_counters", "write_bytes"]),
                _deep_get(end, ["process", "io_counters", "write_bytes"]),
            )
            or 0.0
        )
        totals["proc_read_count"] += (
            _delta(
                _deep_get(start, ["process", "io_counters", "read_count"]),
                _deep_get(end, ["process", "io_counters", "read_count"]),
            )
            or 0.0
        )
        totals["proc_write_count"] += (
            _delta(
                _deep_get(start, ["process", "io_counters", "write_count"]),
                _deep_get(end, ["process", "io_counters", "write_count"]),
            )
            or 0.0
        )
        proc_cpu_pct = _delta(
            _deep_get(start, ["process", "cpu_percent"]),
            _deep_get(end, ["process", "cpu_percent"]),
        )
        if proc_cpu_pct is not None:
            totals["proc_cpu_percent_sum"] += proc_cpu_pct
            totals["proc_cpu_percent_n"] += 1

        for collection, path in [
            (end_proc_threads, ["process", "num_threads"]),
            (end_proc_fds, ["process", "num_open_file_descriptors"]),
            (end_proc_open_files, ["process", "num_open_files"]),
            (end_proc_conns, ["process", "num_connections"]),
            (end_proc_rss, ["process", "memory", "rss"]),
            (end_proc_vms, ["process", "memory", "vms"]),
        ]:
            val = as_float(_deep_get(end, path))
            if val is not None:
                collection.append(val)

        start_gpu = start.get("gpu", {}) if isinstance(start.get("gpu"), dict) else {}
        end_gpu = end.get("gpu", {}) if isinstance(end.get("gpu"), dict) else {}
        for gpu_key, gpu_end in end_gpu.items():
            if not isinstance(gpu_end, dict):
                continue
            gpu_name = gpu_end.get("name")
            if gpu_name:
                gpu_names.add(str(gpu_name))
            gpu_id = gpu_end.get("id")
            if gpu_id:
                gpu_ids.add(str(gpu_id))
            numeric_end: Dict[str, float] = {}
            _flatten_numeric("", gpu_end, numeric_end)
            gpu_start = start_gpu.get(gpu_key, {}) if isinstance(start_gpu.get(gpu_key), dict) else {}
            numeric_start: Dict[str, float] = {}
            _flatten_numeric("", gpu_start, numeric_start)
            for metric, val_end in numeric_end.items():
                val_start = numeric_start.get(metric)
                if val_start is not None and val_end >= val_start:
                    gpu_metric_deltas[metric] += val_end - val_start
                elif metric not in gpu_metric_deltas:
                    gpu_metric_deltas[metric] += val_end
                lower_metric = metric.lower()
                if "temperature" in lower_metric or "hotspot" in lower_metric or "edge" in lower_metric:
                    gpu_temp_peaks[metric] = max(gpu_temp_peaks.get(metric, float("-inf")), val_end)

    n_rows = len(rows)
    return {
        "rows": n_rows,
        "cpu_user": totals["cpu_user"] if n_rows else None,
        "cpu_system": totals["cpu_system"] if n_rows else None,
        "cpu_percent_avg": (totals["cpu_percent_sum"] / totals["cpu_percent_n"]) if totals["cpu_percent_n"] else None,
        "cpu_freq_avg": (sum(end_cpu_freq) / len(end_cpu_freq)) if end_cpu_freq else None,
        "memory_used": totals["memory_used"] if n_rows else None,
        "memory_percent_avg": (sum(end_mem_percent) / len(end_mem_percent)) if end_mem_percent else None,
        "swap_used": totals["swap_used"] if n_rows else None,
        "swap_percent_avg": (sum(end_swap_percent) / len(end_swap_percent)) if end_swap_percent else None,
        "disk_used": totals["disk_used"] if n_rows else None,
        "disk_percent_total": totals["disk_percent"] if n_rows else None,
        "read_bytes": totals["read_bytes"] if n_rows else None,
        "write_bytes": totals["write_bytes"] if n_rows else None,
        "read_count": totals["read_count"] if n_rows else None,
        "write_count": totals["write_count"] if n_rows else None,
        "disk_read_time": totals["disk_read_time"] if n_rows else None,
        "disk_write_time": totals["disk_write_time"] if n_rows else None,
        "disk_busy_time": totals["disk_busy_time"] if n_rows else None,
        "network": totals,
        "network_end_metrics": dict(network_end_metrics),
        "proc_cpu_user": totals["proc_cpu_user"] if n_rows else None,
        "proc_cpu_system": totals["proc_cpu_system"] if n_rows else None,
        "proc_cpu_percent_avg": (
            totals["proc_cpu_percent_sum"] / totals["proc_cpu_percent_n"] if totals["proc_cpu_percent_n"] else None
        ),
        "proc_read_bytes": totals["proc_read_bytes"] if n_rows else None,
        "proc_write_bytes": totals["proc_write_bytes"] if n_rows else None,
        "proc_read_count": totals["proc_read_count"] if n_rows else None,
        "proc_write_count": totals["proc_write_count"] if n_rows else None,
        "proc_threads_max": max(end_proc_threads) if end_proc_threads else None,
        "proc_open_fds_max": max(end_proc_fds) if end_proc_fds else None,
        "proc_open_files_max": max(end_proc_open_files) if end_proc_open_files else None,
        "proc_connections_max": max(end_proc_conns) if end_proc_conns else None,
        "proc_rss_max": max(end_proc_rss) if end_proc_rss else None,
        "proc_vms_max": max(end_proc_vms) if end_proc_vms else None,
        "gpu_names": sorted(gpu_names),
        "gpu_ids": sorted(gpu_ids),
        "gpu_metric_deltas": dict(gpu_metric_deltas),
        "gpu_temp_peaks": gpu_temp_peaks,
    }


def _render_pipeline_structure(
    activities: List[Dict[str, Any]],
) -> str:
    input_data = "   input"
    output_data = "   output"

    rail = "     │"
    down = "     ▼"
    lines = [input_data, rail, down]
    if not activities:
        lines.extend([down, output_data])
    else:
        for i, row in enumerate(activities):
            lines.append(f" {_to_str(row.get('activity_id'))}")
            if i < len(activities) - 1:
                lines.append(rail)
        lines.append(down)
        lines.append(output_data)

    return "## Workflow Structure\n\n```text\n" + "\n".join(lines) + "\n```"


def _timing_insights(activities: List[Dict[str, Any]]) -> List[str]:
    """Generate interpretation lines for timing report."""
    elapsed_rows: List[Tuple[str, float]] = []
    for row in activities:
        e = as_float(row.get("elapsed_median"))
        if e is not None:
            elapsed_rows.append((_to_str(row.get("activity_id")), e))
    lines = ["### Interpretation & Insights"]
    if not elapsed_rows:
        lines.append("- No valid elapsed timings were available.")
        return lines
    slowest = sorted(elapsed_rows, key=lambda x: x[1], reverse=True)[:5]
    fastest = sorted(elapsed_rows, key=lambda x: x[1])[:3]
    lines.append("- Slowest activities: " + ", ".join(f"`{a}` ({v:.3f}s)" for a, v in slowest))
    lines.append("- Fastest activities: " + ", ".join(f"`{a}` ({v:.3f}s)" for a, v in fastest))
    vals = [v for _, v in elapsed_rows]
    lo, hi = _iqr_bounds(vals)
    if lo is not None and hi is not None:
        outliers = [(a, v) for a, v in elapsed_rows if v < lo or v > hi]
        if outliers:
            top_outliers = sorted(outliers, key=lambda x: x[1], reverse=True)[:5]
            lines.append("- Timing outliers (IQR rule): " + ", ".join(f"`{a}` ({v:.3f}s)" for a, v in top_outliers))
        else:
            lines.append("- Timing outliers (IQR rule): none detected.")
    return lines


def render_provenance_card_markdown(
    dataset: Dict[str, Any],
    activities: List[Dict[str, Any]],
    object_summary: Dict[str, Any],
    output_path: Path,
) -> Dict[str, Any]:
    """Render a summarized provenance-card markdown file."""
    workflow = dataset.get("workflow", {}) if isinstance(dataset.get("workflow"), dict) else {}
    tasks = dataset.get("tasks", []) if isinstance(dataset.get("tasks"), list) else []
    objects = dataset.get("objects") or []
    tasks_sorted = sorted(tasks, key=lambda t: as_float(t.get("started_at")) or float("inf"))

    starts = [as_float(t.get("started_at")) for t in tasks if as_float(t.get("started_at")) is not None]
    ends = [as_float(t.get("ended_at")) for t in tasks if as_float(t.get("ended_at")) is not None]
    min_start = min(starts) if starts else None
    max_end = max(ends) if ends else None
    total_elapsed = (max_end - min_start) if (min_start is not None and max_end is not None) else None

    workflow_name_raw = workflow.get("name", "unknown")
    workflow_name = str(workflow_name_raw).strip()
    if not workflow_name:
        workflow_name = "unknown"
    str(workflow.get("workflow_id", "unknown"))
    campaign_id = str(workflow.get("campaign_id", "unknown"))
    workflow_title = workflow_name
    if workflow_title == "unknown":
        workflow_title = None

    status_counts: Dict[str, int] = {}
    for row in activities:
        for status, count in row["status_counts"].items():
            status_counts[status] = status_counts.get(status, 0) + int(count)

    timing_rows = []
    for row in activities:
        timing_rows.append(
            [
                _to_str(row.get("activity_id")),
                _to_str(row.get("status_counts")),
                fmt_timestamp_utc(row.get("started_at_min")),
                fmt_timestamp_utc(row.get("ended_at_max")),
                _fmt_seconds(as_float(row.get("elapsed_median"))),
            ]
        )

    top_slowest = sorted(
        [(_to_str(row.get("activity_id")), as_float(row.get("elapsed_median"))) for row in activities],
        key=lambda x: x[1] if x[1] is not None else -1,
        reverse=True,
    )[:5]

    telemetry_available = any(
        isinstance(t.get("telemetry_at_start"), dict) and isinstance(t.get("telemetry_at_end"), dict)
        for t in tasks_sorted
    )
    resource_rows: List[List[Any]] = []
    io_heavy: List[Tuple[str, float, float]] = []
    cpu_heavy: List[Tuple[str, float]] = []
    mem_heavy: List[Tuple[str, float]] = []
    process_cpu_heavy: List[Tuple[str, float]] = []
    network_heavy: List[Tuple[str, float, float]] = []
    gpu_heavy: List[Tuple[str, float]] = []
    total_mem = 0.0
    total_read = 0.0
    total_write = 0.0
    total_read_ops = 0.0
    total_write_ops = 0.0
    cpu_values: List[float] = []
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
    activity_process_cpu: Dict[str, float] = defaultdict(float)
    activity_net_sent: Dict[str, float] = defaultdict(float)
    activity_net_recv: Dict[str, float] = defaultdict(float)
    activity_gpu: Dict[str, float] = defaultdict(float)

    if telemetry_available:
        for task in tasks_sorted:
            activity = _to_str(task.get("activity_id"))
            if activity not in activity_order:
                activity_order.append(activity)
            start = task.get("telemetry_at_start", {}) if isinstance(task.get("telemetry_at_start"), dict) else {}
            end = task.get("telemetry_at_end", {}) if isinstance(task.get("telemetry_at_end"), dict) else {}
            delta = _compute_telemetry_delta(start, end)
            elapsed_value = elapsed_seconds(task.get("started_at"), task.get("ended_at"))
            if elapsed_value is not None:
                activity_elapsed[activity].append(elapsed_value)
            total_mem += delta["memory_used"] or 0.0
            total_read += delta["read_bytes"] or 0.0
            total_write += delta["write_bytes"] or 0.0
            total_read_ops += delta["read_count"] or 0.0
            total_write_ops += delta["write_count"] or 0.0
            activity_cpu_user[activity] += delta["cpu_user"] or 0.0
            activity_cpu_system[activity] += delta["cpu_system"] or 0.0
            activity_memory[activity] += delta["memory_used"] or 0.0
            activity_read[activity] += delta["read_bytes"] or 0.0
            activity_write[activity] += delta["write_bytes"] or 0.0
            activity_read_ops[activity] += delta["read_count"] or 0.0
            activity_write_ops[activity] += delta["write_count"] or 0.0
            if delta["cpu_percent"] is not None:
                cpu_values.append(delta["cpu_percent"])
                activity_cpu_percent[activity].append(delta["cpu_percent"])
            process_cpu = (
                _delta(
                    _deep_get(start, ["process", "cpu_percent"]),
                    _deep_get(end, ["process", "cpu_percent"]),
                )
                or 0.0
            )
            activity_process_cpu[activity] += process_cpu
            net_sent = (
                _delta(
                    _deep_get(start, ["network", "netio_sum", "bytes_sent"]),
                    _deep_get(end, ["network", "netio_sum", "bytes_sent"]),
                )
                or 0.0
            )
            net_recv = (
                _delta(
                    _deep_get(start, ["network", "netio_sum", "bytes_recv"]),
                    _deep_get(end, ["network", "netio_sum", "bytes_recv"]),
                )
                or 0.0
            )
            activity_net_sent[activity] += net_sent
            activity_net_recv[activity] += net_recv
            task_gpu_delta = 0.0
            start_gpu = start.get("gpu", {}) if isinstance(start.get("gpu"), dict) else {}
            end_gpu = end.get("gpu", {}) if isinstance(end.get("gpu"), dict) else {}
            for gpu_key, gpu_end in end_gpu.items():
                if not isinstance(gpu_end, dict):
                    continue
                flat_end: Dict[str, float] = {}
                _flatten_numeric("", gpu_end, flat_end)
                flat_start: Dict[str, float] = {}
                gpu_start = start_gpu.get(gpu_key, {}) if isinstance(start_gpu.get(gpu_key), dict) else {}
                _flatten_numeric("", gpu_start, flat_start)
                for metric, v_end in flat_end.items():
                    if "used" not in metric.lower() or "gpu" in metric.lower():
                        continue
                    v_start = flat_start.get(metric)
                    if v_start is not None and v_end >= v_start:
                        task_gpu_delta += v_end - v_start
                    else:
                        task_gpu_delta += v_end
            activity_gpu[activity] += task_gpu_delta

        for activity in activity_order:
            elapsed_values = sorted(activity_elapsed.get(activity, []))
            elapsed_median = _percentile(elapsed_values, 0.50) if elapsed_values else None
            cpu_percent_values = activity_cpu_percent.get(activity, [])
            cpu_percent_avg = (sum(cpu_percent_values) / len(cpu_percent_values)) if cpu_percent_values else None
            resource_rows.append(
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

        io_heavy = sorted(
            [
                (activity, activity_read.get(activity, 0.0), activity_write.get(activity, 0.0))
                for activity in activity_order
            ],
            key=lambda x: x[1] + x[2],
            reverse=True,
        )
        cpu_heavy = sorted(
            [
                (
                    activity,
                    (
                        (sum(activity_cpu_percent.get(activity, [])) / len(activity_cpu_percent.get(activity, [])))
                        if activity_cpu_percent.get(activity)
                        else 0.0
                    ),
                )
                for activity in activity_order
            ],
            key=lambda x: x[1],
            reverse=True,
        )
        mem_heavy = sorted(
            [(activity, activity_memory.get(activity, 0.0)) for activity in activity_order],
            key=lambda x: x[1],
            reverse=True,
        )
        process_cpu_heavy = sorted(
            [(activity, activity_process_cpu.get(activity, 0.0)) for activity in activity_order],
            key=lambda x: x[1],
            reverse=True,
        )
        network_heavy = sorted(
            [
                (activity, activity_net_sent.get(activity, 0.0), activity_net_recv.get(activity, 0.0))
                for activity in activity_order
            ],
            key=lambda x: x[1] + x[2],
            reverse=True,
        )
        gpu_heavy = sorted(
            [(activity, activity_gpu.get(activity, 0.0)) for activity in activity_order],
            key=lambda x: x[1],
            reverse=True,
        )
    avg_cpu = (sum(cpu_values) / len(cpu_values)) if cpu_values else None
    telemetry_overview = _extract_telemetry_overview(tasks_sorted) if telemetry_available else {}
    has_real_telemetry = int(telemetry_overview.get("rows", 0) or 0) > 0

    code_repo = workflow.get("code_repository", {}) if isinstance(workflow.get("code_repository"), dict) else {}
    code_repo_text = (
        f"branch={_to_str(code_repo.get('branch'))}, "
        f"short_sha={_to_str(code_repo.get('short_sha'))}, "
        f"dirty={_to_str(code_repo.get('dirty'))}"
    )

    lines: List[str] = []
    if workflow_title is None:
        lines.append("# Workflow Provenance Card")
    else:
        lines.append(f"# Workflow Provenance Card: {workflow_title}")
    lines.append("")
    lines.append("## Summary")
    _append_summary_line(lines, "Workflow Name", workflow_name)
    _append_summary_line(lines, "Campaign ID", campaign_id)
    _append_summary_line(lines, "Execution Start (UTC)", fmt_timestamp_utc(min_start))
    _append_summary_line(lines, "Execution End (UTC)", fmt_timestamp_utc(max_end))
    _append_summary_line(lines, "Total Elapsed (s)", _fmt_seconds(total_elapsed))
    _append_summary_line(lines, "User", _to_str(workflow.get("user")))
    _append_summary_line(lines, "System Name", _to_str(workflow.get("sys_name")))
    _append_summary_line(lines, "Environment ID", _to_str(workflow.get("environment_id")))
    if workflow.get("subtype") is not None:
        _append_summary_line(lines, "Workflow Subtype", _to_str(workflow.get("subtype")))
    if not (
        _is_empty_metric(_to_str(code_repo.get("branch")))
        and _is_empty_metric(_to_str(code_repo.get("short_sha")))
        and _is_empty_metric(_to_str(code_repo.get("dirty")))
    ):
        lines.append(f"- **Code Repository:** `{code_repo_text}`")
    _append_summary_line(lines, "Git Remote", _to_str(code_repo.get("remote")))
    for section_label, section_key in [
        ("Workflow Used", "used"),
        ("Workflow Generated", "generated"),
        ("Workflow Custom Metadata", "custom_metadata"),
    ]:
        section_data = workflow.get(section_key)
        if not isinstance(section_data, dict) or not section_data:
            continue
        lines.append(f"- **{section_label}:**")
        for key in sorted(section_data.keys()):
            value = section_data[key]
            if isinstance(value, (dict, list)) and value:
                lines.append(f"  - `{key}`:")
                lines.append("    ```yaml")
                for row in _format_nested_metadata_lines(value):
                    lines.append(f"    {row}")
                lines.append("    ```")
            else:
                rendered = _format_single_field_value(value)
                lines.append(f"  - `{key}`: `{rendered}`")
    lines.append("")

    lines.append("## Workflow-level Summary")
    lines.append(f"- **Total Activities:** `{len(activities)}`")
    lines.append(f"- **Status Counts:** `{status_counts}`")
    lines.append(f"- **Total Elapsed Workflow Time (s):** `{_fmt_seconds(total_elapsed)}`")
    slowest_items = [(name, sec) for name, sec in top_slowest if sec is not None]
    if len(activities) > 5 and slowest_items:
        lines.append("- **Top 5 Slowest Activities:**")
    for name, sec in slowest_items:
        lines.append(f"  - `{name}`: `{_fmt_seconds(sec)} s`")
    if has_real_telemetry:
        resource_total_lines: List[str] = []
        memory_text = _fmt_bytes(total_mem)
        cpu_text = _fmt_percent(avg_cpu)
        read_text = _fmt_bytes(total_read)
        write_text = _fmt_bytes(total_write)
        read_ops_text = _fmt_count(total_read_ops)
        write_ops_text = _fmt_count(total_write_ops)
        if not _is_empty_metric(memory_text):
            resource_total_lines.append(f"  - `Memory Used`: `{memory_text}`")
        if not _is_empty_metric(cpu_text):
            resource_total_lines.append(f"  - `Average CPU (%)`: `{cpu_text}`")
        io_lines: List[str] = []
        if not _is_empty_metric(read_text):
            io_lines.append(f"    - `Read`: `{read_text}`")
        if not _is_empty_metric(write_text):
            io_lines.append(f"    - `Write`: `{write_text}`")
        if not _is_empty_metric(read_ops_text):
            io_lines.append(f"    - `Read Ops`: `{read_ops_text}`")
        if not _is_empty_metric(write_ops_text):
            io_lines.append(f"    - `Write Ops`: `{write_ops_text}`")
        if io_lines:
            resource_total_lines.append("  - **IO:**")
            resource_total_lines.extend(io_lines)
        if resource_total_lines:
            lines.append("- **Resource Totals:**")
            lines.extend(resource_total_lines)

        observation_lines: List[str] = []
        if top_slowest and top_slowest[0][1] is not None:
            observation_lines.append(
                f"  - Slowest Activity: `{top_slowest[0][0]}` at `{_fmt_seconds(top_slowest[0][1])} s`"
            )
        if io_heavy:
            top_io = io_heavy[0]
            top_read_text = _fmt_bytes(top_io[1])
            top_write_text = _fmt_bytes(top_io[2])
            if not (_is_empty_metric(top_read_text) and _is_empty_metric(top_write_text)):
                observation_lines.append(
                    f"  - Largest IO Activity: `{top_io[0]}` with Read `{top_read_text}` and Write `{top_write_text}`"
                )
        if observation_lines:
            lines.append("- **Key Observations:**")
            lines.extend(observation_lines)
    lines.append("")
    lines.append(_render_pipeline_structure(activities))
    lines.append("")

    lines.append("## Timing Report")
    lines.append("Rows are sorted by **First Started At** (ascending).")
    lines.append("")
    lines.append(
        _render_table(
            ["Activity", "Status Counts", "First Started At", "Last Ended At", "Median Elapsed (s)"],
            timing_rows,
        )
    )
    lines.append("")
    lines.extend(_timing_insights(activities))
    lines.append("")
    lines.extend(_build_activity_io_summary(tasks_sorted))

    if has_real_telemetry:
        gpu_device_count = len(telemetry_overview.get("gpu_names", [])) or len(telemetry_overview.get("gpu_ids", []))
        peak_gpu_temp = None
        if telemetry_overview.get("gpu_temp_peaks"):
            peak_gpu_temp = max(telemetry_overview["gpu_temp_peaks"].values())
        gpu_used_delta = None
        gpu_power_delta = None
        if telemetry_overview.get("gpu_metric_deltas"):
            used_values = [
                v
                for k, v in telemetry_overview["gpu_metric_deltas"].items()
                if "used" in k.lower() and "gpu" not in k.lower()
            ]
            power_values = [v for k, v in telemetry_overview["gpu_metric_deltas"].items() if "power" in k.lower()]
            gpu_used_delta = sum(used_values) if used_values else None
            gpu_power_delta = sum(power_values) if power_values else None

        net_metrics = telemetry_overview.get("network", {})
        net_err_in = _fmt_count(net_metrics.get("net_errin"))
        net_err_out = _fmt_count(net_metrics.get("net_errout"))
        net_drop_in = _fmt_count(net_metrics.get("net_dropin"))
        net_drop_out = _fmt_count(net_metrics.get("net_dropout"))
        gpu_names = telemetry_overview.get("gpu_names", [])
        gpu_ids = telemetry_overview.get("gpu_ids", [])
        gpu_names_text = ", ".join(gpu_names) if gpu_names else "-"
        gpu_ids_text = ", ".join(gpu_ids) if gpu_ids else "-"

        workflow_resource_rows = [
            ["Telemetry Samples (task start/end pairs)", telemetry_overview.get("rows", 0)],
            ["CPU User Time Delta", _fmt_seconds(telemetry_overview.get("cpu_user"))],
            ["CPU System Time Delta", _fmt_seconds(telemetry_overview.get("cpu_system"))],
            ["Average CPU (%) Delta", _fmt_percent(telemetry_overview.get("cpu_percent_avg"))],
            ["Average CPU Frequency", _fmt_count(telemetry_overview.get("cpu_freq_avg"))],
            ["Memory Used Delta", _fmt_bytes(telemetry_overview.get("memory_used"))],
            ["Average Memory (%)", _fmt_percent(telemetry_overview.get("memory_percent_avg"))],
            ["Swap Used Delta", _fmt_bytes(telemetry_overview.get("swap_used"))],
            ["Average Swap (%)", _fmt_percent(telemetry_overview.get("swap_percent_avg"))],
            ["Disk Used Delta", _fmt_bytes(telemetry_overview.get("disk_used"))],
            ["Disk Read Time Delta (ms)", _fmt_seconds(telemetry_overview.get("disk_read_time"))],
            ["Disk Write Time Delta (ms)", _fmt_seconds(telemetry_overview.get("disk_write_time"))],
            ["Disk Busy Time Delta (ms)", _fmt_seconds(telemetry_overview.get("disk_busy_time"))],
            ["Network Sent", _fmt_bytes(net_metrics.get("net_bytes_sent"))],
            ["Network Received", _fmt_bytes(net_metrics.get("net_bytes_recv"))],
            ["Network Packets Sent", _fmt_count(net_metrics.get("net_packets_sent"))],
            ["Network Packets Received", _fmt_count(net_metrics.get("net_packets_recv"))],
            ["Network Errors In/Out", f"{net_err_in} / {net_err_out}"],
            ["Network Drops In/Out", f"{net_drop_in} / {net_drop_out}"],
            ["Process CPU User Delta (s)", _fmt_nonzero_seconds(telemetry_overview.get("proc_cpu_user"))],
            ["Process CPU System Delta (s)", _fmt_nonzero_seconds(telemetry_overview.get("proc_cpu_system"))],
            ["Process CPU (%) Delta", _fmt_percent(telemetry_overview.get("proc_cpu_percent_avg"))],
            ["Process IO Read", _fmt_bytes(telemetry_overview.get("proc_read_bytes"))],
            ["Process IO Write", _fmt_bytes(telemetry_overview.get("proc_write_bytes"))],
            ["Process IO Read Ops", _fmt_count(telemetry_overview.get("proc_read_count"))],
            ["Process IO Write Ops", _fmt_count(telemetry_overview.get("proc_write_count"))],
            ["Process Max RSS", _fmt_bytes(telemetry_overview.get("proc_rss_max"))],
            ["Process Max VMS", _fmt_bytes(telemetry_overview.get("proc_vms_max"))],
            ["Process Max Threads", _fmt_count(telemetry_overview.get("proc_threads_max"))],
            ["Process Max Open Files", _fmt_count(telemetry_overview.get("proc_open_files_max"))],
            ["Process Max Open FDs", _fmt_count(telemetry_overview.get("proc_open_fds_max"))],
            ["Process Max Connections", _fmt_count(telemetry_overview.get("proc_connections_max"))],
            ["GPU Devices Seen", _fmt_count(gpu_device_count)],
            ["GPU Names", gpu_names_text],
            ["GPU IDs", gpu_ids_text],
            ["GPU Used Delta", _fmt_bytes(gpu_used_delta)],
            ["GPU Power Delta", f"{gpu_power_delta:.3f}" if gpu_power_delta is not None else "-"],
            ["Peak GPU Temperature", f"{peak_gpu_temp:.3f}" if peak_gpu_temp is not None else "-"],
        ]
        workflow_resource_rows = [row for row in workflow_resource_rows if not _is_empty_metric(row[1])]
        insight_lines: List[str] = []
        if not _is_empty_metric(_fmt_percent(telemetry_overview.get("cpu_percent_avg"))):
            cpu_avg = _fmt_percent(telemetry_overview.get("cpu_percent_avg"))
            insight_lines.append(f"- CPU-heavy period (avg delta): `{cpu_avg}`.")
        if not _is_empty_metric(_fmt_bytes(telemetry_overview.get("memory_used"))):
            insight_lines.append(
                "- Memory pressure (delta): "
                f"`{_fmt_bytes(telemetry_overview.get('memory_used'))}`; "
                f"peak RSS: `{_fmt_bytes(telemetry_overview.get('proc_rss_max'))}`."
            )
        if not _is_empty_metric(_fmt_bytes(total_read)) or not _is_empty_metric(_fmt_bytes(total_write)):
            insight_lines.append(
                f"- Disk IO pressure: read `{_fmt_bytes(total_read)}`, write `{_fmt_bytes(total_write)}`."
            )
        if not _is_empty_metric(_fmt_bytes(net_metrics.get("net_bytes_sent"))) or not _is_empty_metric(
            _fmt_bytes(net_metrics.get("net_bytes_recv"))
        ):
            insight_lines.append(
                "- Network movement: sent "
                f"`{_fmt_bytes(net_metrics.get('net_bytes_sent'))}`, received "
                f"`{_fmt_bytes(net_metrics.get('net_bytes_recv'))}`."
            )
        if not _is_empty_metric(_fmt_seconds(telemetry_overview.get("proc_cpu_user"))) or not _is_empty_metric(
            _fmt_seconds(telemetry_overview.get("proc_cpu_system"))
        ):
            insight_lines.append(
                "- Process-level pressure: "
                f"cpu_user_delta=`{_fmt_seconds(telemetry_overview.get('proc_cpu_user'))}`, "
                f"cpu_system_delta=`{_fmt_seconds(telemetry_overview.get('proc_cpu_system'))}`."
            )
        if gpu_device_count:
            insight_lines.append(
                f"- GPU activity detected on `{gpu_device_count}` device(s); peak temperature: `{peak_gpu_temp:.3f}`."
            )
        show_workflow_resource_section = bool(workflow_resource_rows or insight_lines)
        if show_workflow_resource_section:
            lines.append("## Workflow-level Resource Usage")
            if workflow_resource_rows:
                lines.append(_render_table(["Metric", "Value"], workflow_resource_rows))
                lines.append("")
            if insight_lines:
                lines.append("### Interpretation & Insights")
                lines.extend(insight_lines)
                lines.append("")

        per_activity_headers = [
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
        per_activity_headers, resource_rows = _filter_all_empty_columns(
            per_activity_headers,
            resource_rows,
            keep_indices=[0, 1],
        )
        per_activity_insight_lines: List[str] = []
        if any((read_b + write_b) > 0 for _, read_b, write_b in io_heavy):
            per_activity_insight_lines.append("- Most IO-heavy Activities (Read + Write):")
            for name, read_b, write_b in io_heavy[:5]:
                if read_b + write_b <= 0:
                    continue
                per_activity_insight_lines.append(
                    f"  - `{name}`: Read={_fmt_bytes(read_b)}, Write={_fmt_bytes(write_b)}"
                )
        if any(cpu_pct > 0 for _, cpu_pct in cpu_heavy):
            per_activity_insight_lines.append("- Most CPU-active Activities:")
            for name, cpu_pct in cpu_heavy[:5]:
                if cpu_pct <= 0:
                    continue
                per_activity_insight_lines.append(f"  - `{name}`: CPU={_fmt_percent(cpu_pct)}")
        if any(mem > 0 for _, mem in mem_heavy):
            per_activity_insight_lines.append("- Largest memory growth Activities:")
            for name, mem in mem_heavy[:5]:
                if mem <= 0:
                    continue
                per_activity_insight_lines.append(f"  - `{name}`: Memory Delta={_fmt_bytes(mem)}")
        if any((sent + recv) > 0 for _, sent, recv in network_heavy):
            per_activity_insight_lines.append("- Most network-active Activities:")
            for name, sent, recv in network_heavy[:5]:
                if sent + recv <= 0:
                    continue
                per_activity_insight_lines.append(f"  - `{name}`: Sent={_fmt_bytes(sent)}, Received={_fmt_bytes(recv)}")
        if any(proc_cpu > 0 for _, proc_cpu in process_cpu_heavy):
            per_activity_insight_lines.append("- Highest process CPU delta Activities:")
            for name, proc_cpu in process_cpu_heavy[:5]:
                if proc_cpu <= 0:
                    continue
                per_activity_insight_lines.append(f"  - `{name}`: Process CPU Delta={_fmt_percent(proc_cpu)}")
        if any(gpu_delta > 0 for _, gpu_delta in gpu_heavy):
            per_activity_insight_lines.append("- Highest GPU memory delta Activities:")
            for name, gpu_delta in gpu_heavy[:5]:
                if gpu_delta <= 0:
                    continue
                per_activity_insight_lines.append(f"  - `{name}`: GPU Used Delta={_fmt_bytes(gpu_delta)}")
        per_activity_has_resource_values = any(
            any(not _is_empty_metric(cell) for cell in row[2:]) for row in resource_rows
        )
        show_per_activity_resource_section = bool(per_activity_has_resource_values or per_activity_insight_lines)
        if show_per_activity_resource_section:
            lines.append("## Per-activity Resource Usage")
            if per_activity_has_resource_values:
                lines.append(_render_table(per_activity_headers, resource_rows))
                lines.append("")
            if per_activity_insight_lines:
                lines.append("### Interpretation & Insights")
                lines.extend(per_activity_insight_lines)
                lines.append("")

    total_objects = int(object_summary.get("total_objects", 0) or 0)
    if total_objects > 0:
        lines.append("## Object Artifacts Summary")
        lines.append(
            _render_table(
                ["Metric", "Value"],
                [
                    ["Total Objects", total_objects],
                    ["By Type", object_summary.get("by_type", {})],
                    ["By Storage", object_summary.get("by_storage", {})],
                    ["Task-linked Objects", object_summary.get("task_linked", 0)],
                    ["Workflow-linked Objects", object_summary.get("workflow_linked", 0)],
                    ["Max Version", object_summary.get("max_version", "unknown")],
                    ["Total Size", _fmt_bytes(object_summary.get("total_size_bytes"))],
                    ["Average Size", _fmt_bytes(object_summary.get("avg_size_bytes"))],
                    ["Max Size", _fmt_bytes(object_summary.get("max_size_bytes"))],
                ],
            )
        )
        lines.extend(_build_object_details_lines(objects))
        lines.append("")

    has_aggregated_activity = any(int(row.get("n_tasks", 0) or 0) > 1 for row in activities)
    if has_aggregated_activity:
        lines.append("## Aggregation Method")
        lines.append("- Grouping key: `activity_id`.")
        lines.append("- Each grouped row may aggregate multiple task records (`n_tasks`).")
        lines.append("- Aggregated metrics currently include count/status/timing.")
        lines.append("")

    lines.append("---")
    generated_at = datetime.now().astimezone().strftime("%b %d, %Y at %I:%M %p %Z")
    lines.append(
        "Provenance card generated by [Flowcept](https://flowcept.org/) | "
        "[GitHub](https://github.com/ORNL/flowcept) | "
        f"[Version: {__version__}](https://github.com/ORNL/flowcept/releases/tag/v{__version__}) "
        f"on {generated_at}"
    )
    lines.append("")

    content = "\n".join(lines)
    if output_path is not None:
        output_path.write_text(content, encoding="utf-8")
    return {
        "output": str(output_path) if output_path is not None else None,
        "markdown": content,
        "tasks": len(tasks),
        "activities": len(activities),
        "objects": int(object_summary.get("total_objects", 0)),
    }
