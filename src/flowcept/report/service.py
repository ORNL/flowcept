"""Service layer for Flowcept report generation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List

from flowcept.report.aggregations import group_activities, summarize_objects
from flowcept.report.loaders import load_records_from_db, read_jsonl, split_records
from flowcept.report.renderers.provenance_campaign_card_markdown import render_provenance_campaign_card_markdown
from flowcept.report.renderers.provenance_card_markdown import (
    render_markdown_file_into_rich_terminal,
    render_provenance_card_markdown,
)
from flowcept.report.renderers.provenance_report_pdf import render_provenance_report_pdf


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


def generate_report(
    report_type: str = "provenance_card",
    format: str = "markdown",
    print_markdown: bool = False,
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
    print_markdown : bool, optional
        If True and the output format is markdown, print the rendered markdown
        to terminal after generation using Rich.
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
    mode = _resolve_input_mode(
        input_jsonl_path=input_jsonl_path,
        records=records,
        workflow_id=workflow_id,
        campaign_id=campaign_id,
    )

    if report_type not in {"provenance_card", "provenance_report"}:
        raise ValueError(f"Unsupported report_type: {report_type}")
    if format not in {"markdown", "pdf"}:
        raise ValueError(f"Unsupported format: {format}")
    if report_type == "provenance_card" and format != "markdown":
        raise ValueError("provenance_card supports only markdown format.")
    if report_type == "provenance_report" and format != "pdf":
        raise ValueError("provenance_report supports only pdf format.")

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

    is_campaign = "workflows" in dataset

    if output_path is None:
        if is_campaign:
            output_path = "CAMPAIGN_PROVENANCE_CARD.md"
        else:
            output_path = "PROVENANCE_CARD.md" if report_type == "provenance_card" else "PROVENANCE_REPORT.pdf"
    output = Path(output_path)

    if is_campaign:
        # Campaign dataset: multiple workflow runs detected
        render_stats = render_provenance_campaign_card_markdown(
            dataset=dataset,
            output_path=output,
        )
    else:
        activities = group_activities(dataset.get("tasks", []))
        object_summary = summarize_objects(dataset.get("objects", []))
        if format == "markdown":
            render_stats = render_provenance_card_markdown(
                dataset=dataset,
                activities=activities,
                object_summary=object_summary,
                output_path=output,
            )
        else:
            render_stats = render_provenance_report_pdf(
                dataset=dataset,
                activities=activities,
                object_summary=object_summary,
                output_path=output,
            )

    if format == "markdown" and print_markdown:
        if importlib.util.find_spec("rich") is None:
            raise ModuleNotFoundError(
                'Markdown terminal rendering requires Rich. Install with: pip install flowcept["extras"]'
            )
        render_markdown_file_into_rich_terminal(output)

    return {
        "report_type": report_type,
        "format": format,
        "output": str(output),
        "input_mode": mode,
        "skipped_lines": skipped_lines,
        **render_stats,
    }
