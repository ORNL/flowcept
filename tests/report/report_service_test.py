import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flowcept import Flowcept


def _sample_records():
    return [
        {
            "type": "workflow",
            "workflow_id": "wf-1",
            "campaign_id": "camp-1",
            "name": "demo_wf",
        },
        {
            "type": "task",
            "workflow_id": "wf-1",
            "campaign_id": "camp-1",
            "task_id": "t1",
            "activity_id": "LoadData",
            "status": "FINISHED",
            "started_at": 10.0,
            "ended_at": 15.0,
            "custom_metadata": {"current_stage": "ingest"},
        },
        {
            "type": "task",
            "workflow_id": "wf-1",
            "campaign_id": "camp-1",
            "task_id": "t2",
            "activity_id": "LoadData",
            "status": "FINISHED",
            "started_at": 16.0,
            "ended_at": 22.0,
            "custom_metadata": {"current_stage": "ingest"},
        },
        {
            "type": "task",
            "workflow_id": "wf-1",
            "campaign_id": "camp-1",
            "task_id": "t3",
            "activity_id": "Transform",
            "status": "FINISHED",
            "started_at": 23.0,
            "ended_at": 25.0,
            "custom_metadata": {"current_stage": "transform"},
        },
        {
            "object_id": "obj-1",
            "workflow_id": "wf-1",
            "task_id": "t3",
            "object_type": "ml_model",
            "version": 1,
            "grid_fs_file_id": "abc123",
            "object_size_bytes": 4096,
            "data": b"should-not-be-rendered",
        },
    ]


def _sample_records_with_telemetry_and_io():
    return [
        {
            "type": "workflow",
            "workflow_id": "wf-tele-1",
            "campaign_id": "camp-tele-1",
            "name": "telemetry_demo",
            "sys_name": "Darwin",
            "environment_id": "laptop",
            "code_repository": {
                "branch": "main",
                "short_sha": "abc123",
                "dirty": "clean",
                "remote": "git@example/repo.git",
            },
        },
        {
            "type": "task",
            "workflow_id": "wf-tele-1",
            "campaign_id": "camp-tele-1",
            "task_id": "t1",
            "activity_id": "LoadData",
            "status": "FINISHED",
            "started_at": 10.0,
            "ended_at": 20.0,
            "used": {"input_path": "data/a.json", "batch": 16},
            "generated": {"rows": 1000},
            "telemetry_at_start": {
                "cpu": {"times_avg": {"user": 1.0, "system": 0.5}, "percent_all": 10.0},
                "disk": {"io_sum": {"read_bytes": 1000, "write_bytes": 200, "read_count": 10, "write_count": 2}},
                "memory": {"virtual": {"used": 10000}},
            },
            "telemetry_at_end": {
                "cpu": {"times_avg": {"user": 2.5, "system": 1.0}, "percent_all": 35.0},
                "disk": {"io_sum": {"read_bytes": 7000, "write_bytes": 1200, "read_count": 25, "write_count": 6}},
                "memory": {"virtual": {"used": 18000}},
            },
        },
        {
            "type": "task",
            "workflow_id": "wf-tele-1",
            "campaign_id": "camp-tele-1",
            "task_id": "t2",
            "activity_id": "Transform",
            "status": "FINISHED",
            "started_at": 21.0,
            "ended_at": 23.0,
            "used": {"output_dir": "out/demo", "batch": 32},
            "generated": {"rows": 500},
            "telemetry_at_start": {
                "cpu": {"times_avg": {"user": 2.0, "system": 1.0}, "percent_all": 20.0},
                "disk": {"io_sum": {"read_bytes": 7000, "write_bytes": 1200, "read_count": 25, "write_count": 6}},
                "memory": {"virtual": {"used": 18000}},
            },
            "telemetry_at_end": {
                "cpu": {"times_avg": {"user": 2.8, "system": 1.5}, "percent_all": 45.0},
                "disk": {"io_sum": {"read_bytes": 9000, "write_bytes": 4200, "read_count": 35, "write_count": 18}},
                "memory": {"virtual": {"used": 24000}},
            },
            "custom_metadata": {"metadata": {"saved_files": ["out/demo/data.pt"]}},
        },
    ]


class ReportServiceTests(unittest.TestCase):
    def test_generate_report_per_activity_resource_usage_is_aggregated_by_activity_id(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-resource-agg-1",
                "campaign_id": "camp-resource-agg-1",
                "name": "resource_agg_demo",
            },
            {
                "type": "task",
                "workflow_id": "wf-resource-agg-1",
                "campaign_id": "camp-resource-agg-1",
                "task_id": "t1",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 10.0,
                "ended_at": 12.0,
                "telemetry_at_start": {"cpu": {"times_avg": {"user": 1.0, "system": 0.2}}},
                "telemetry_at_end": {"cpu": {"times_avg": {"user": 2.0, "system": 0.5}}},
            },
            {
                "type": "task",
                "workflow_id": "wf-resource-agg-1",
                "campaign_id": "camp-resource-agg-1",
                "task_id": "t2",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 13.0,
                "ended_at": 15.0,
                "telemetry_at_start": {"cpu": {"times_avg": {"user": 2.0, "system": 0.5}}},
                "telemetry_at_end": {"cpu": {"times_avg": {"user": 2.8, "system": 0.9}}},
            },
            {
                "type": "task",
                "workflow_id": "wf-resource-agg-1",
                "campaign_id": "camp-resource-agg-1",
                "task_id": "t3",
                "activity_id": "Transform",
                "status": "FINISHED",
                "started_at": 16.0,
                "ended_at": 17.0,
                "telemetry_at_start": {"cpu": {"times_avg": {"user": 2.8, "system": 0.9}}},
                "telemetry_at_end": {"cpu": {"times_avg": {"user": 3.2, "system": 1.1}}},
            },
        ]

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            section = content.split("## Per-activity Resource Usage", 1)[1]
            section = section.split("\n## ", 1)[0]
            assert section.count("| LoadData |") == 1
            assert section.count("| Transform |") == 1

    def test_generate_report_single_activity_tags_render_only_when_present(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-tags-1",
                "campaign_id": "camp-tags-1",
                "name": "tags_demo",
            },
            {
                "type": "task",
                "workflow_id": "wf-tags-1",
                "campaign_id": "camp-tags-1",
                "task_id": "t1",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 10.0,
                "ended_at": 11.0,
                "tags": ["important"],
            },
            {
                "type": "task",
                "workflow_id": "wf-tags-1",
                "campaign_id": "camp-tags-1",
                "task_id": "t2",
                "activity_id": "Transform",
                "status": "FINISHED",
                "started_at": 11.0,
                "ended_at": 12.0,
                "tags": [],
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            assert "  - Tag: `important`" in content
            assert "  - Tags:" not in content

    def test_generate_report_hides_unknown_workflow_name_in_title(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-no-name-1",
                "campaign_id": "camp-no-name-1",
            },
            {
                "type": "task",
                "workflow_id": "wf-no-name-1",
                "campaign_id": "camp-no-name-1",
                "task_id": "t1",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 10.0,
                "ended_at": 11.0,
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            assert "# Workflow Card\n" in content
            assert "# Workflow Card:" not in content
            assert "- **Workflow Name:** `unknown`" not in content

    def test_generate_report_hides_empty_workflow_name_in_title(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-empty-name-1",
                "campaign_id": "camp-empty-name-1",
                "name": "",
            },
            {
                "type": "task",
                "workflow_id": "wf-empty-name-1",
                "campaign_id": "camp-empty-name-1",
                "task_id": "t1",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 10.0,
                "ended_at": 11.0,
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            assert "# Workflow Card\n" in content
            assert "# Workflow Card:" not in content
            assert "- **Workflow Name:** `unknown`" not in content

    def test_generate_report_from_records(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            stats = Flowcept.generate_report(records=_sample_records(), output_path=str(output))
            assert output.exists()
            assert stats["input_mode"] == "records"
            content = output.read_text(encoding="utf-8")
            assert "## Aggregation Method" in content
            assert "## Object Artifacts Summary" in content
            assert "## Per Activity Details" in content
            assert "- **Total Activities:** `2`" in content
            assert "- **Status Counts:** `{'FINISHED': 3}`" in content
            assert "| Total Size | 4.00 KB |" in content
            assert "| Average Size | 4.00 KB |" in content
            assert "- **User:** `unknown`" not in content
            assert "- **System Name:** `unknown`" not in content
            assert "- **Environment ID:** `unknown`" not in content

    def test_generate_report_hides_empty_resource_sections_and_aggregation(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-no-resource-1",
                "campaign_id": "camp-no-resource-1",
                "name": "no_resource_demo",
            },
            {
                "type": "task",
                "workflow_id": "wf-no-resource-1",
                "campaign_id": "camp-no-resource-1",
                "task_id": "t1",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 10.0,
                "ended_at": 11.0,
            },
            {
                "type": "task",
                "workflow_id": "wf-no-resource-1",
                "campaign_id": "camp-no-resource-1",
                "task_id": "t2",
                "activity_id": "Transform",
                "status": "FINISHED",
                "started_at": 11.0,
                "ended_at": 12.0,
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            assert "## Workflow-level Resource Usage" not in content
            assert "## Per-activity Resource Usage" not in content
            assert "## Aggregation Method" not in content

    def test_generate_report_hides_resource_sections_for_empty_telemetry_snapshots(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-empty-tele-1",
                "campaign_id": "camp-empty-tele-1",
                "name": "empty_telemetry_demo",
            },
            {
                "type": "task",
                "workflow_id": "wf-empty-tele-1",
                "campaign_id": "camp-empty-tele-1",
                "task_id": "t1",
                "activity_id": "LoadData",
                "status": "FINISHED",
                "started_at": 10.0,
                "ended_at": 11.0,
                "telemetry_at_start": {},
                "telemetry_at_end": {},
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            assert "## Workflow-level Resource Usage" not in content
            assert "## Per-activity Resource Usage" not in content

    def test_generate_report_from_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl_path = Path(td) / "flowcept_buffer.jsonl"
            with jsonl_path.open("w", encoding="utf-8") as f:
                for rec in _sample_records():
                    rec_copy = dict(rec)
                    if isinstance(rec_copy.get("data"), (bytes, bytearray)):
                        rec_copy["data"] = "bytes-redacted"
                    f.write(json.dumps(rec_copy) + "\n")
            output = Path(td) / "card.md"
            stats = Flowcept.generate_report(input_jsonl_path=str(jsonl_path), output_path=str(output))
            assert output.exists()
            assert stats["input_mode"] == "jsonl"

    def test_generate_report_input_validation(self):
        with self.assertRaises(ValueError):
            Flowcept.generate_report(
                input_jsonl_path="/tmp/a.jsonl",
                records=[],
            )

    def test_generate_report_from_db_mode_dispatch(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "db_card.md"
            mocked_dataset = {
                "workflow": {"workflow_id": "wf-1", "campaign_id": "camp-1", "name": "demo_wf"},
                "tasks": _sample_records()[1:4],
                "objects": [_sample_records()[4]],
            }
            with patch("flowcept.report.service.load_records_from_db", return_value=mocked_dataset) as mocked:
                stats = Flowcept.generate_report(workflow_id="wf-1", output_path=str(output))
                assert output.exists()
                assert stats["input_mode"] == "db"
                mocked.assert_called_once()

    def test_generate_report_contains_insights_sections(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            stats = Flowcept.generate_report(records=_sample_records_with_telemetry_and_io(), output_path=str(output))
            assert output.exists()
            assert stats["input_mode"] == "records"
            content = output.read_text(encoding="utf-8")
            assert "## Timing Report" in content
            assert "### Interpretation & Insights" in content
            assert "Slowest activities:" in content
            assert "Fastest activities:" in content
            assert "## Per Activity Details" in content
            assert "Activities with richest **used** metadata" in content
            assert "Activities with richest **generated** metadata" in content
            assert "## Workflow-level Resource Usage" in content
            assert "## Per-activity Resource Usage" in content
            assert "Most IO-heavy Activities (Read + Write):" in content
            assert "Most CPU-active Activities:" in content
            assert "## Object Artifacts Summary" not in content
            assert "No per-Activity telemetry insights were available." not in content

    def test_generate_report_pdf_from_records(self):
        try:
            import matplotlib  # noqa: F401
            import reportlab  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("PDF dependencies are not installed.")

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "PROVENANCE_REPORT.pdf"
            stats = Flowcept.generate_report(
                report_type="provenance_report",
                records=_sample_records_with_telemetry_and_io(),
                format="pdf",
                output_path=str(output),
            )
            assert output.exists()
            assert stats["input_mode"] == "records"
            assert stats["format"] == "pdf"
            assert stats["report_type"] == "provenance_report"
            assert stats.get("plots", 0) >= 1

    def test_generate_report_rejects_mismatched_card_pdf(self):
        with self.assertRaises(ValueError):
            Flowcept.generate_report(
                report_type="workflow_card",
                format="pdf",
                records=_sample_records(),
            )

    def test_generate_report_lists_up_to_five_latest_objects_per_type(self):
        records = [
            {
                "type": "workflow",
                "workflow_id": "wf-obj-1",
                "campaign_id": "camp-obj-1",
                "name": "object_demo",
            }
        ]

        for i in range(6):
            records.append(
                {
                    "object_id": f"model-{i}",
                    "workflow_id": "wf-obj-1",
                    "task_id": f"task-{i}",
                    "object_type": "ml_model",
                    "version": i,
                    "utc_timestamp": float(100 + i),
                    "object_size_bytes": 1024 + i,
                    "storage_type": "gridfs",
                    "custom_metadata": {"loss": round(i * 0.1, 3)},
                }
            )

        for i in range(2):
            records.append(
                {
                    "object_id": f"dataset-{i}",
                    "workflow_id": "wf-obj-1",
                    "task_id": f"dataset-task-{i}",
                    "object_type": "dataset",
                    "version": i,
                    "utc_timestamp": float(200 + i),
                    "object_size_bytes": 2048 + i,
                    "storage_type": "in_object",
                    "custom_metadata": {"source": f"input-{i}.csv"},
                }
            )

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            stats = Flowcept.generate_report(records=records, output_path=str(output))
            assert output.exists()
            assert stats["input_mode"] == "records"
            content = output.read_text(encoding="utf-8")

            assert "- **Models:**" in content
            assert "- **Datasets:**" in content
            assert "`custom_metadata`:" in content
            assert "model-5" in content
            assert "model-0" not in content
            assert "Latest 5" not in content

    def test_generate_report_keeps_generic_title_for_ml_workflow_subtype(self):
        records = _sample_records_with_telemetry_and_io()
        records[0]["subtype"] = "ml_workflow"
        records[1]["subtype"] = "dataprep"
        records[2]["subtype"] = "learning"
        records.append(
            {
                "object_id": "model-ml-1",
                "workflow_id": "wf-tele-1",
                "task_id": "t2",
                "object_type": "ml_model",
                "version": 2,
                "storage_type": "gridfs",
                "custom_metadata": {"loss": 0.125},
            }
        )
        records.append(
            {
                "object_id": "dataset-ml-1",
                "workflow_id": "wf-tele-1",
                "task_id": "t1",
                "object_type": "dataset",
                "version": 1,
                "storage_type": "in_object",
            }
        )
        records[2]["generated"]["val_loss"] = 0.2
        records[2]["generated"]["val_accuracy"] = 0.9

        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            Flowcept.generate_report(records=records, output_path=str(output))
            content = output.read_text(encoding="utf-8")
            assert "# Workflow Card: telemetry_demo" in content
            assert "## ML Workflow Insights" not in content
            assert "- **Workflow Subtype:** `ml_workflow`" in content
            assert "- **LoadData** (subtype=`dataprep`)" in content
            assert "- **Transform** (subtype=`learning`)" in content

    def test_generate_report_print_markdown_renders_when_rich_available(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            with (
                patch("flowcept.report.service.importlib.util.find_spec", return_value=object()),
                patch("flowcept.report.service.render_markdown_file_into_rich_terminal") as mocked_render,
            ):
                Flowcept.generate_report(
                    records=_sample_records(),
                    output_path=str(output),
                    print_markdown=True,
                )
                mocked_render.assert_called_once_with(output)

    def test_generate_report_print_markdown_raises_when_rich_missing(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "WORKFLOW_CARD.md"
            with patch("flowcept.report.service.importlib.util.find_spec", return_value=None):
                with self.assertRaises(ModuleNotFoundError) as ctx:
                    Flowcept.generate_report(
                        records=_sample_records(),
                        output_path=str(output),
                        print_markdown=True,
                    )
            assert 'flowcept["extras"]' in str(ctx.exception)
