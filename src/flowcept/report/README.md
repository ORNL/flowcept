# flowcept.report

This package implements Flowcept's provenance report generation pipeline. It produces human-readable provenance artifacts from workflow execution records captured by Flowcept, supporting both single-workflow and multi-workflow campaign scenarios.

## Overview

Flowcept captures task, workflow, and object records during the execution of scientific and ML workflows. The `report` package transforms those records into structured provenance documents that summarize what ran, where, how long it took, what resources were consumed, and what artifacts were produced.

## Package Structure

```
report/
├── service.py                  # Entry point: orchestrates loading, aggregation, and rendering
├── loaders.py                  # Data loading from JSONL files, in-memory records, or DB
├── aggregations.py             # Activity grouping, timing statistics, hostname extraction
├── sanitization.py             # Redacts sensitive fields before rendering
└── renderers/
    ├── provenance_card_markdown.py          # Single-workflow markdown report
    ├── provenance_campaign_card_markdown.py # Multi-workflow campaign markdown report
    └── provenance_report_pdf.py             # Single-workflow PDF report (requires matplotlib + reportlab)
```

## Report Types

### Single-workflow provenance card (markdown)
Generated when the input data contains a single `workflow_id`. Covers workflow overview, activity timing, resource telemetry, per-activity detail, and object artifact summary.

### Campaign provenance card (markdown)
Generated automatically when the input data contains multiple `workflow_id` values sharing a `campaign_id`. Two sub-types are handled:

- **Replicated runs** — multiple runs of the same abstract workflow (same `workflow_name`). Focuses on cross-run comparison: timing trends, per-activity breakdown across runs, and execution host distribution.
- **Pipeline** — multiple runs of different abstract workflows (different `workflow_name`s). Focuses on stage-by-stage progression: pipeline overview, per-stage mini-cards with hostname and resource details, and a unified object artifact summary.

### Provenance report (PDF)
Full PDF report for a single workflow, including matplotlib visualizations: activity bar charts, DAG structure, and ML learning curves when applicable.

## Usage

```python
from flowcept import Flowcept

# From a JSONL buffer file
Flowcept.generate_report(input_jsonl_path="buffer.jsonl")

# From DB by workflow or campaign
Flowcept.generate_report(workflow_id="<id>")
Flowcept.generate_report(campaign_id="<id>")

# PDF format
Flowcept.generate_report(workflow_id="<id>", report_type="provenance_report", format="pdf")
```

Via CLI:
```bash
flowcept generate_report buffer.jsonl
flowcept generate_report buffer.jsonl --format pdf
```

## Transparency Note

Most of the code in this package was developed with AI assistance, for transparency:

- **Claude claude-sonnet-4-6** (Anthropic) — used via Claude Code (the Anthropic CLI) for design, implementation, and iterative refinement of the report pipeline.
- **Codex (OpenAI o3-mini / model 5.2)** — used for additional code generation and review passes during development.
