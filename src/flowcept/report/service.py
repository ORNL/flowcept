"""Service layer for Flowcept report generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from flowcept.report.aggregations import group_transformations, summarize_objects
from flowcept.report.loaders import load_records_from_db, read_jsonl, split_records
from flowcept.report.renderers.provenance_card_markdown import render_provenance_card_markdown


def _resolve_input_mode(
    input_jsonl_path: str | None,
    records: List[Dict[str, Any]] | None,
    workflow_id: str | None,
    campaign_id: str | None,
) -> str:
    """Resolve and validate the report input mode."""
    modes = 0
    if input_jsonl_path is not None:
        modes += 1
    if records is not None:
        modes += 1
    if workflow_id is not None or campaign_id is not None:
        modes += 1
    if modes != 1:
        raise ValueError("Provide exactly one input mode: input_jsonl_path OR records OR workflow_id/campaign_id.")
    if input_jsonl_path is not None:
        return "jsonl"
    if records is not None:
        return "records"
    return "db"


def build_provenance_card(
    input_jsonl_path: str | None = None,
    records: List[Dict[str, Any]] | None = None,
    workflow_id: str | None = None,
    campaign_id: str | None = None,
) -> Dict[str, Any]:
    """Build the structured provenance-card content without rendering it.

    Accepts exactly one input mode (JSONL path, pre-loaded records, or DB query
    by workflow/campaign id) and returns the aggregated structures consumed by
    renderers and APIs.

    Parameters
    ----------
    input_jsonl_path : str, optional
        Path to a Flowcept JSONL buffer file.
    records : list of dict, optional
        Pre-loaded Flowcept records (workflow/task/object dicts).
    workflow_id : str, optional
        Workflow identifier for DB query mode.
    campaign_id : str, optional
        Campaign identifier for DB query mode.

    Returns
    -------
    dict
        ``{"dataset", "transformations", "object_summary", "input_mode", "skipped_lines"}``.
    """
    mode = _resolve_input_mode(
        input_jsonl_path=input_jsonl_path,
        records=records,
        workflow_id=workflow_id,
        campaign_id=campaign_id,
    )

    skipped_lines = 0
    if mode == "jsonl":
        jsonl_path = Path(input_jsonl_path)  # type: ignore[arg-type]
        if not jsonl_path.exists():
            raise FileNotFoundError(f"Input JSONL not found: {jsonl_path}")
        parsed_records, skipped_lines = read_jsonl(jsonl_path)
        dataset = split_records(parsed_records)
    elif mode == "records":
        dataset = split_records(records or [])
    else:
        dataset = load_records_from_db(workflow_id=workflow_id, campaign_id=campaign_id)

    return {
        "dataset": dataset,
        "transformations": group_transformations(dataset.get("tasks", [])),
        "object_summary": summarize_objects(dataset.get("objects", [])),
        "input_mode": mode,
        "skipped_lines": skipped_lines,
    }


def generate_report(
    report_type: str = "provenance_card",
    format: str = "markdown",
    output_path: str | None = None,
    input_jsonl_path: str | None = None,
    records: List[Dict[str, Any]] | None = None,
    workflow_id: str | None = None,
    campaign_id: str | None = None,
) -> Dict[str, Any]:
    """Generate a Flowcept report from JSONL, records, or DB query input.

    Parameters
    ----------
    report_type : str, optional
        Report identifier. Default is ``"provenance_card"``.
    format : str, optional
        Output format. Default is ``"markdown"``.
    output_path : str, optional
        Output file path. If omitted, defaults to ``PROVENANCE_CARD.md``.
    input_jsonl_path : str, optional
        Path to a Flowcept JSONL buffer file.
    records : list of dict, optional
        Pre-loaded Flowcept records (workflow/task/object dicts).
    workflow_id : str, optional
        Workflow identifier for DB query mode.
    campaign_id : str, optional
        Campaign identifier for DB query mode.

    Returns
    -------
    dict
        Report generation statistics and output path.
    """
    if report_type != "provenance_card":
        raise ValueError(f"Unsupported report_type: {report_type}")
    if format != "markdown":
        raise ValueError(f"Unsupported format: {format}")

    if output_path is None:
        output_path = "PROVENANCE_CARD.md"
    output = Path(output_path)

    card = build_provenance_card(
        input_jsonl_path=input_jsonl_path,
        records=records,
        workflow_id=workflow_id,
        campaign_id=campaign_id,
    )
    render_stats = render_provenance_card_markdown(
        dataset=card["dataset"],
        transformations=card["transformations"],
        object_summary=card["object_summary"],
        output_path=output,
    )
    return {
        "report_type": report_type,
        "format": format,
        "output": str(output),
        "input_mode": card["input_mode"],
        "skipped_lines": card["skipped_lines"],
        **render_stats,
    }
