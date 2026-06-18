import json
import os
import tempfile
from time import sleep
import unittest

import pytest
from unittest.mock import patch

import pandas as pd

from flowcept.agents import ToolResult
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT, INSTRUMENTATION_ENABLED, MQ_ENABLED
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.instrumentation.flowcept_task import flowcept_task

class TestAgent(unittest.TestCase):

    @flowcept_task
    def offline_buffer_task(x, y):
        return x + y

    def setUp(self):
        if not AGENT.get("enabled", False):
            FlowceptLogger().warning("Skipping agent tests because agent is disabled.")
            self.skipTest("Agent is disabled.")

    def test_loads_jsonl_buffer_when_mq_disabled(self):
        if not os.environ.get("FLOWCEPT_SETTINGS_PATH"):
            FlowceptLogger().warning("Skipping no-MQ agent buffer test because FLOWCEPT_SETTINGS_PATH is not set.")
            self.skipTest("FLOWCEPT_SETTINGS_PATH is not set.")
        if MQ_ENABLED:
            FlowceptLogger().warning("Skipping no-MQ agent buffer test because MQ is enabled.")
            self.skipTest("MQ is enabled.")
        if not INSTRUMENTATION_ENABLED:
            FlowceptLogger().warning("Skipping no-MQ agent buffer test because instrumentation is disabled.")
            self.skipTest("Instrumentation is disabled.")

        from flowcept.agents.mcp import mcp_server as agent_module

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as handle:
            buffer_path = handle.name

        with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False) as f:
            TestAgent.offline_buffer_task(1, 2)
            f.dump_buffer(path=buffer_path)

        agent = agent_module.FlowceptAgent(buffer_path=buffer_path)
        agent.start()
        try:
            sleep(0.5)
            resp = agent.query("how many tasks?")
            tool_result = ToolResult(**json.loads(resp))
            self.assertTrue(tool_result.code in {201, 301})
        finally:
            agent.stop()

    def test_mcp_db_backed_provenance_tools(self):
        """The shared prov tools are exposed as MCP tools and query the real DB."""
        from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
        from flowcept.configs import MONGO_ENABLED

        if not MONGO_ENABLED:
            FlowceptLogger().warning("Skipping MCP DB tools test because MongoDB is disabled.")
            self.skipTest("MongoDB is disabled.")
        if not Flowcept.services_alive():
            FlowceptLogger().warning("Skipping MCP DB tools test because services are not alive.")
            self.skipTest("Flowcept services are not alive.")

        from uuid import uuid4

        from flowcept.agents.mcp import mcp_server as agent_module
        from flowcept.agents.mcp.mcp_client import run_tool
        from flowcept.instrumentation.task_capture import FlowceptTask

        campaign_id = f"mcp-campaign-{uuid4()}"
        with Flowcept(campaign_id=campaign_id, workflow_name=f"mcp-tools-wf-{uuid4()}"):
            workflow_id = Flowcept.current_workflow_id
            with FlowceptTask(activity_id="mcp_seed", used={"x": 1}) as task:
                task.end(generated={"y": 2})

        deadline = 20
        while deadline > 0 and not (Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []):
            sleep(0.5)
            deadline -= 1

        agent = agent_module.FlowceptAgent()
        agent.start()
        try:
            resp = run_tool("query_tasks", kwargs={"filter": {"workflow_id": workflow_id}})[0]
            tool_result = ToolResult(**json.loads(resp))
            self.assertIn(tool_result.code, {201, 301})
            items = tool_result.result["items"]
            self.assertTrue(any(t["activity_id"] == "mcp_seed" for t in items))

            resp = run_tool("list_campaigns", kwargs={})[0]
            tool_result = ToolResult(**json.loads(resp))
            self.assertIn(tool_result.code, {201, 301})
            self.assertTrue(any(c["campaign_id"] == campaign_id for c in tool_result.result["items"]))
        finally:
            agent.stop()
            if DocumentDBDAO._instance is not None:
                DocumentDBDAO._instance.close()


class TestDbQueryToolsIntegration(unittest.TestCase):
    """Integration tests for data_query_tools/db_query_tools.py.

    Requires real MongoDB + Redis services.  Guards skip when unavailable.
    """

    def setUp(self):
        from flowcept.configs import MONGO_ENABLED

        if not MONGO_ENABLED:
            FlowceptLogger().warning("Skipping db_query_tools integration tests: MongoDB disabled.")
            self.skipTest("MongoDB is disabled.")
        if not Flowcept.services_alive():
            FlowceptLogger().warning("Skipping db_query_tools integration tests: services not alive.")
            self.skipTest("Flowcept services are not alive.")

    def test_i2_query_tasks_returns_seeded_task(self):
        """query_tasks returns tasks matching a workflow_id filter."""
        from uuid import uuid4
        from flowcept.agents.data_query_tools.db_query_tools import query_tasks
        from flowcept.instrumentation.task_capture import FlowceptTask
        from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO

        campaign_id = f"dqt-test-{uuid4()}"
        with Flowcept(campaign_id=campaign_id, workflow_name=f"dqt-wf-{uuid4()}"):
            workflow_id = Flowcept.current_workflow_id
            with FlowceptTask(activity_id="dqt_activity", used={"p": 42}) as task:
                task.end(generated={"result": 99})

        deadline = 20
        while deadline > 0 and not (Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []):
            sleep(0.5)
            deadline -= 1

        result = query_tasks(filter={"workflow_id": workflow_id})
        self.assertIn(result.code, {201, 301})
        items = result.result["items"]
        self.assertTrue(any(t["activity_id"] == "dqt_activity" for t in items))

        try:
            if DocumentDBDAO._instance is not None:
                DocumentDBDAO._instance.close()
        except Exception:
            pass

    def test_i2_list_campaigns_includes_seeded_campaign(self):
        """list_campaigns returns a campaign for a seeded workflow."""
        from uuid import uuid4
        from flowcept.agents.data_query_tools.db_query_tools import list_campaigns
        from flowcept.instrumentation.task_capture import FlowceptTask
        from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO

        campaign_id = f"dqt-campaign-{uuid4()}"
        with Flowcept(campaign_id=campaign_id, workflow_name=f"dqt-wf-{uuid4()}"):
            workflow_id = Flowcept.current_workflow_id
            with FlowceptTask(activity_id="dqt_campaign_activity") as task:
                task.end()

        deadline = 20
        while deadline > 0 and not (Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []):
            sleep(0.5)
            deadline -= 1

        result = list_campaigns()
        self.assertIn(result.code, {201, 301})
        campaigns = result.result["items"]
        self.assertTrue(any(c["campaign_id"] == campaign_id for c in campaigns))

        try:
            if DocumentDBDAO._instance is not None:
                DocumentDBDAO._instance.close()
        except Exception:
            pass

    def test_i2_validate_filter_rejects_disallowed_operator(self):
        """validate_filter raises ValueError for operators not in the allowlist."""
        from flowcept.agents.data_query_tools.db_query_tools import validate_filter

        with self.assertRaises(ValueError):
            validate_filter({"status": {"$where": "this.x > 0"}})

    def test_i2_query_tasks_rejects_bad_filter(self):
        """query_tasks returns an error code when given a disallowed filter operator."""
        from flowcept.agents.data_query_tools.db_query_tools import query_tasks

        result = query_tasks(filter={"status": {"$where": "this.x > 0"}})
        self.assertTrue(result.code >= 400, f"Expected error code, got {result.code}")


class TestAgentInMemoryQueryTools(unittest.TestCase):
    class _DummyContext:
        def __init__(self, df, schema, value_examples, custom_user_guidance):
            self.request_context = type("ReqCtx", (), {})()
            self.request_context.lifespan_context = type("LifeCtx", (), {})()
            self.request_context.lifespan_context.df = df
            self.request_context.lifespan_context.tasks_schema = schema
            self.request_context.lifespan_context.value_examples = value_examples
            self.request_context.lifespan_context.custom_guidance = custom_user_guidance

    def test_build_df_query_prompt_returns_prompt_payload(self):
        from flowcept.agents.prompts import mcp_prompts as t

        df = pd.DataFrame({"activity_id": ["a", "b"], "used.x": [1, 2]})
        schema = {"activity_a": {"i": ["used.x"], "o": []}}
        value_examples = {"x": {"t": "int", "v": [1, 2]}}
        guidance = ["prefer concise outputs"]
        dummy_ctx = self._DummyContext(
            df=df,
            schema=schema,
            value_examples=value_examples,
            custom_user_guidance=guidance,
        )

        with patch.object(t.mcp_flowcept, "get_context", return_value=dummy_ctx):
            prompt_text = t.build_df_query_prompt(query="count tasks by activity")

        self.assertIsInstance(prompt_text, str)
        self.assertIn("ALLOWED_FIELDS", prompt_text)
        self.assertIn("activity_id", prompt_text)
        self.assertIn("count tasks by activity", prompt_text)

    def test_build_df_query_prompt_returns_404_when_df_missing(self):
        from flowcept.agents.prompts import mcp_prompts as t

        dummy_ctx = self._DummyContext(df=pd.DataFrame(), schema={}, value_examples={}, custom_user_guidance=[])
        with patch.object(t.mcp_flowcept, "get_context", return_value=dummy_ctx):
            prompt_text = t.build_df_query_prompt(query="anything")

        self.assertEqual(prompt_text, "Current df is empty or null.")

    def test_execute_generated_df_code_runs_against_current_df(self):
        from flowcept.agents.mcp.mcp_tools import in_memory_task_query_mcp_tools as t

        df = pd.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]})
        dummy_ctx = self._DummyContext(df=df, schema={}, value_examples={}, custom_user_guidance=[])

        with patch.object(t.mcp_flowcept, "get_context", return_value=dummy_ctx):
            tool_result = t.execute_generated_df_code(user_code="result = df[['a']].head(2)")

        self.assertEqual(tool_result.code, 301)
        self.assertIn("result_df", tool_result.result)
        self.assertIn("a", tool_result.result["result_df"])
        self.assertIn("1", tool_result.result["result_df"])
        self.assertIn("2", tool_result.result["result_df"])

    def test_generate_workflow_card_tool(self):
        from flowcept.agents.mcp.mcp_tools import report_tools as g

        expected_stats = {"markdown": "# Workflow Card: Demo\n\nBody"}

        with patch.object(Flowcept, "generate_report", return_value=expected_stats) as mocked:
            tool_result = g.generate_workflow_card(workflow_id="wf-1")

        self.assertEqual(tool_result.code, 301)
        self.assertEqual(tool_result.result["workflow_id"], "wf-1")
        self.assertIn("markdown", tool_result.result)
        self.assertIn("Workflow Card", tool_result.result["markdown"])
        mocked.assert_called_once_with(
            report_type="workflow_card",
            format="markdown",
            workflow_id="wf-1",
            campaign_id=None,
            input_jsonl_path=None,
        )


    def test_llm_query_over_buffer(self):
        if not AGENT.get("api_key"):
            FlowceptLogger().warning("Skipping LLM agent query test because agent.api_key is not set.")
            self.skipTest("agent.api_key is not set.")
        if not os.environ.get("FLOWCEPT_SETTINGS_PATH"):
            FlowceptLogger().warning("Skipping LLM agent query test because FLOWCEPT_SETTINGS_PATH is not set.")
            self.skipTest("FLOWCEPT_SETTINGS_PATH is not set.")
        if MQ_ENABLED:
            FlowceptLogger().warning("Skipping LLM agent query test because MQ is enabled.")
            self.skipTest("MQ is enabled.")
        if not INSTRUMENTATION_ENABLED:
            FlowceptLogger().warning("Skipping LLM agent query test because instrumentation is disabled.")
            self.skipTest("Instrumentation is disabled.")
        if not AGENT.get("service_provider"):
            FlowceptLogger().warning("Skipping LLM agent query test because service_provider is not set.")
            self.skipTest("Agent service_provider is not set.")

        if AGENT.get("api_key"):
            key = AGENT.get("api_key")
            masked = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else key
            print(f"Using agent.api_key: {masked}")

        from flowcept.agents.mcp import mcp_server as agent_module

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as buffer_handle:
            buffer_path = buffer_handle.name

        with Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False) as f:
            TestAgent.offline_buffer_task(1, 2)
            f.dump_buffer(path=buffer_path)

        agent = agent_module.FlowceptAgent(buffer_path=buffer_path)
        agent.start()
        try:
            sleep(0.5)
            resp = agent.query("how many tasks?")
            tool_result = ToolResult(**json.loads(resp))

            print(f"LLM response: {tool_result.result}")
            self.assertTrue(tool_result.code in {201, 301})
        finally:
            agent.stop()


class TestSchemaIntrospection(unittest.TestCase):
    """Unit tests for static_schema_builder.py — no services, no LLM required."""

    def test_get_attribute_docstrings_returns_documented_fields(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import get_attribute_docstrings

        class _Documented:
            foo: str = None
            """Description of foo."""
            bar: int = None
            """Description of bar."""

        docs = get_attribute_docstrings(_Documented)
        self.assertEqual(docs["foo"], "Description of foo.")
        self.assertEqual(docs["bar"], "Description of bar.")

    def test_get_attribute_docstrings_excludes_undocumented(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import get_attribute_docstrings

        class _Mixed:
            documented: str = None
            """Has a docstring."""
            undocumented: int = None

        docs = get_attribute_docstrings(_Mixed)
        self.assertIn("documented", docs)
        self.assertNotIn("undocumented", docs)

    def test_assert_schema_documented_passes_on_full_coverage(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import assert_schema_documented

        class _Full:
            x: str = None
            """Describes x."""
            y: float = None
            """Describes y."""

        assert_schema_documented(_Full)  # must not raise

    def test_assert_schema_documented_raises_on_missing(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import assert_schema_documented, SchemaDocumentationError

        class _Partial:
            good: str = None
            """Has a docstring."""
            bad: int = None

        with self.assertRaises(SchemaDocumentationError) as ctx:
            assert_schema_documented(_Partial)
        self.assertIn("bad", str(ctx.exception))
        self.assertIn("_Partial", str(ctx.exception))

    def test_assert_schema_documented_error_message_is_actionable(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import assert_schema_documented, SchemaDocumentationError

        class _Empty:
            field_a: str = None
            field_b: int = None

        with self.assertRaises(SchemaDocumentationError) as ctx:
            assert_schema_documented(_Empty)
        msg = str(ctx.exception)
        self.assertIn("field_a", msg)
        self.assertIn("field_b", msg)
        self.assertIn("triple-quoted", msg)

    def test_domain_classes_all_documented(self):
        """All domain classes must pass the startup assert — catches regressions."""
        from flowcept.agents.provenance_schema_manager.static_schema_builder import assert_schema_documented
        from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
        from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject
        from flowcept.commons.flowcept_dataclasses.blob_object import BlobObject
        from flowcept.commons.task_data_preprocess import (
            TelemetrySummary, CpuSummary, MemorySummary, DiskSummary, NetworkSummary,
        )

        assert_schema_documented(
            TaskObject, WorkflowObject, AgentObject, BlobObject,
            TelemetrySummary, CpuSummary, MemorySummary, DiskSummary, NetworkSummary,
        )

    def test_build_schema_context_returns_expected_keys(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import build_schema_context

        ctx = build_schema_context()
        for key in ("task_fields", "workflow_fields", "agent_fields", "blob_fields", "telemetry_summary_fields"):
            self.assertIn(key, ctx)
            self.assertIsInstance(ctx[key], list)
            self.assertTrue(len(ctx[key]) > 0, f"{key} must not be empty")

    def test_build_schema_context_task_fields_have_required_keys(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import build_schema_context

        ctx = build_schema_context()
        field_names = {f["name"] for f in ctx["task_fields"]}
        for expected in ("task_id", "workflow_id", "activity_id", "started_at", "ended_at", "hostname"):
            self.assertIn(expected, field_names)

    def test_build_schema_context_telemetry_expands_subfields(self):
        from flowcept.agents.provenance_schema_manager.static_schema_builder import build_schema_context

        ctx = build_schema_context()
        field_names = {f["name"] for f in ctx["telemetry_summary_fields"]}
        for expected in (
            "duration_sec",
            "cpu.percent_all_diff",
            "memory.used_mem_diff",
            "disk.read_bytes_diff",
            "network.bytes_sent_diff",
        ):
            self.assertIn(expected, field_names)

    def test_telemetry_summary_fields_match_summarize_telemetry_output(self):
        """TelemetrySummary schema must match the actual keys produced by summarize_telemetry()."""
        from flowcept.agents.provenance_schema_manager.static_schema_builder import get_attribute_docstrings
        from flowcept.commons.task_data_preprocess import (
            CpuSummary, MemorySummary, DiskSummary, NetworkSummary,
            summarize_telemetry,
        )

        cpu = {"percent_all": 10.0, "times_avg": {"user": 1.0, "system": 0.5, "idle": 8.5}}
        disk = {"io_sum": {"read_bytes": 100, "write_bytes": 50, "read_count": 5, "write_count": 3}}
        memory = {"virtual": {"used": 1024, "percent": 50.0}, "swap": {"used": 0}}
        network = {"netio_sum": {"bytes_sent": 200, "bytes_recv": 300, "packets_sent": 2, "packets_recv": 3}}

        task = {
            "started_at": 1000.0,
            "ended_at": 1042.7,
            "telemetry_at_start": {"cpu": cpu, "disk": disk, "memory": memory, "network": network},
            "telemetry_at_end": {
                "cpu": {"percent_all": 20.0, "times_avg": {"user": 2.0, "system": 1.0, "idle": 7.0}},
                "disk": {"io_sum": {"read_bytes": 200, "write_bytes": 100, "read_count": 10, "write_count": 6}},
                "memory": {"virtual": {"used": 2048, "percent": 60.0}, "swap": {"used": 128}},
                "network": {"netio_sum": {"bytes_sent": 400, "bytes_recv": 600, "packets_sent": 4, "packets_recv": 6}},
            },
        }

        import logging
        logger = logging.getLogger("test")
        result = summarize_telemetry(task, logger)

        sub_map = {"cpu": CpuSummary, "memory": MemorySummary, "disk": DiskSummary, "network": NetworkSummary}
        for section, sub_cls in sub_map.items():
            self.assertIn(section, result, f"summarize_telemetry must produce '{section}' key")
            schema_keys = set(get_attribute_docstrings(sub_cls).keys())
            actual_keys = set(result[section].keys())
            self.assertEqual(schema_keys, actual_keys, f"{sub_cls.__name__} schema mismatch for '{section}'")

    def test_lifespan_override_runs_schema_assert_and_populates_context(self):
        """Importing the ctx manager module triggers no errors and the lifespan method is overridden."""
        from flowcept.agents.context_manager import FlowceptAgentContextManager
        from flowcept.agents.provenance_schema_manager.static_schema_builder import assert_schema_documented, build_schema_context, SCHEMA_CONTEXT

        # Confirm the override is defined directly on FlowceptAgentContextManager (not just inherited).
        self.assertIn("lifespan", FlowceptAgentContextManager.__dict__)

        # Simulate what the lifespan does at startup (sans the async machinery).
        from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
        from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject
        from flowcept.commons.flowcept_dataclasses.blob_object import BlobObject
        from flowcept.commons.task_data_preprocess import (
            TelemetrySummary, CpuSummary, MemorySummary, DiskSummary, NetworkSummary,
        )
        # Should not raise — all domain classes are fully documented.
        assert_schema_documented(
            TaskObject, WorkflowObject, AgentObject, BlobObject,
            TelemetrySummary, CpuSummary, MemorySummary, DiskSummary, NetworkSummary,
        )
        ctx = build_schema_context()
        SCHEMA_CONTEXT.update(ctx)
        self.assertEqual(set(SCHEMA_CONTEXT.keys()), {
            "task_fields", "workflow_fields", "agent_fields", "blob_fields", "telemetry_summary_fields"
        })
        # SCHEMA_CONTEXT is populated in the module; check it is the same object.
        from flowcept.agents.provenance_schema_manager import static_schema_builder as si
        self.assertIs(SCHEMA_CONTEXT, si.SCHEMA_CONTEXT)


class TestRefactoredAgentStructure(unittest.TestCase):
    """Structural import tests for the C/D/E/F refactor.

    All tests are pure import / attribute checks — no live services needed.
    TDD: these tests are written first; they fail until the refactor is implemented.
    """

    # ── C4: ToolResult extracted to tool_result.py ────────────────────────
    def test_c4_tool_result_importable_from_new_module(self):
        from flowcept.agents.tool_result import ToolResult
        r = ToolResult(code=201, result="ok")
        self.assertTrue(r.is_success())
        self.assertTrue(r.result_is_str())

    # ── C5: build_llm_model + normalize_message in llm/builders.py ────────
    def test_c5_llm_builders_importable(self):
        from flowcept.agents.llm.builders import build_llm_model, normalize_message
        self.assertTrue(callable(build_llm_model))
        self.assertEqual(normalize_message(" Hello? "), "hello")

    def test_c5_no_python_imports_use_agents_utils_shim(self):
        from pathlib import Path

        forbidden = "flowcept.agents." + "agents_utils"
        offenders = []
        for root in ("src", "tests", "examples"):
            for path in Path(root).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if forbidden in text:
                    offenders.append(str(path))

        self.assertEqual(offenders, [])

    # ── C6: llm/providers/ has LLM wrappers ───────────────────────────────
    def test_c6_llm_providers_modules_importable(self):
        import flowcept.agents.llm.providers.claude_gcp as cg
        import flowcept.agents.llm.providers.gemini25 as g
        self.assertTrue(hasattr(cg, "ClaudeOnGCPLLM"))
        self.assertTrue(hasattr(g, "Gemini25LLM"))

    # ── C1: mcp_server.py (was flowcept_agent.py) ─────────────────────────
    def test_c1_mcp_server_importable(self):
        from flowcept.agents.mcp.mcp_server import FlowceptAgent
        self.assertTrue(callable(FlowceptAgent))

    # ── C2: mcp_client.py (was agent_client.py) ───────────────────────────
    def test_c2_mcp_client_importable(self):
        from flowcept.agents.mcp.mcp_client import run_tool, run_prompt
        self.assertTrue(callable(run_tool))
        self.assertTrue(callable(run_prompt))

    def test_c2_no_python_imports_use_duplicate_agent_client(self):
        from pathlib import Path

        forbidden = "flowcept.agents.mcp." + "agent_client"
        offenders = []
        for root in ("src", "tests", "examples"):
            for path in Path(root).rglob("*.py"):
                text = path.read_text(encoding="utf-8")
                if forbidden in text:
                    offenders.append(str(path))

        self.assertEqual(offenders, [])

    def test_c2_maintained_docs_do_not_reference_removed_agent_paths(self):
        from pathlib import Path

        forbidden_terms = [
            "flowcept.agents.agent_client",
            "flowcept.agents.flowcept_agent",
            "src/flowcept/agents/tools/prov_tools.py",
            "src/flowcept/agents/agents_utils.py",
        ]
        paths = [
            Path("docs/agent.rst"),
            Path("docs/README.md"),
            Path("src/flowcept/agents/README.md"),
            Path("agent_sandbox/test_agent_jsonl_smoke.py"),
        ]

        offenders = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            for term in forbidden_terms:
                if term in text:
                    offenders.append(f"{path}: {term}")

        self.assertEqual(offenders, [])

    # ── C3: context_manager.py (was flowcept_ctx_manager.py) ──────────────
    def test_c3_context_manager_importable(self):
        from flowcept.agents.context_manager import (
            ctx_manager,
            mcp_flowcept,
        )
        self.assertIsNotNone(ctx_manager)
        self.assertEqual(mcp_flowcept.name, "FlowceptAgent")

    # ── C9/C10: data_query_tools/ and mcp_tools/ packages exist ──────────
    def test_c9_data_query_tools_package_exists(self):
        import flowcept.agents.data_query_tools as dqt
        self.assertTrue(hasattr(dqt, "__path__"))

    def test_c10_mcp_tools_package_exists(self):
        import flowcept.agents.mcp.mcp_tools as mt
        self.assertTrue(hasattr(mt, "__path__"))

    # ── D1: db_query_tools.py ─────────────────────────────────────────────
    def test_d1_db_query_tools_importable(self):
        from flowcept.agents.data_query_tools.db_query_tools import (
            query_tasks,
            ALLOWED_FILTER_OPERATORS,
            validate_filter,
        )
        self.assertIn("$eq", ALLOWED_FILTER_OPERATORS)
        self.assertTrue(callable(query_tasks))
        validate_filter({"status": {"$eq": "FINISHED"}})  # must not raise

    def test_d1_db_query_tools_not_decorated_with_mcp(self):
        from flowcept.agents.data_query_tools import db_query_tools
        import inspect
        for name in ("query_tasks", "query_workflows", "get_task_summary"):
            fn = getattr(db_query_tools, name)
            src = inspect.getsource(fn)
            self.assertNotIn("@mcp_flowcept", src, f"{name} must not have @mcp_flowcept decorator")

    def test_d1_db_query_tools_does_not_import_webservice(self):
        import inspect

        from flowcept.agents.data_query_tools import db_query_tools

        self.assertNotIn("flowcept.webservice", inspect.getsource(db_query_tools))

    # ── D2: in_memory_task_query_tools.py ─────────────────────────────────
    def test_d2_in_memory_task_query_tools_importable(self):
        from flowcept.agents.data_query_tools.in_memory_task_query_tools import (
            run_df_query,
        )
        self.assertTrue(callable(run_df_query))

    def test_d2_in_memory_task_query_tools_no_mcp_decorator(self):
        from flowcept.agents.data_query_tools import in_memory_task_query_tools as t
        import inspect
        for name in ("run_df_query", "generate_result_df", "run_df_code"):
            fn = getattr(t, name)
            src = inspect.getsource(fn)
            self.assertNotIn("@mcp_flowcept", src, f"{name} must not have @mcp_flowcept decorator")

    # ── D3: pandas_utils.py ───────────────────────────────────────────────
    def test_d3_pandas_utils_importable(self):
        from flowcept.agents.data_query_tools.pandas_utils import (
            safe_execute,
        )
        self.assertTrue(callable(safe_execute))

    # ── D4: in_memory_workflow_query_tools.py ─────────────────────────────
    def test_d4_in_memory_workflow_query_tools_importable(self):
        from flowcept.agents.data_query_tools.in_memory_workflow_query_tools import (
            execute_generated_workflow_query,
            _resolve_path,
        )
        self.assertTrue(callable(execute_generated_workflow_query))
        self.assertEqual(_resolve_path({"a": {"b": 1}}, "a.b"), 1)

    def test_d4_in_memory_workflow_query_tools_no_mcp_decorator(self):
        from flowcept.agents.data_query_tools import in_memory_workflow_query_tools as t
        import inspect
        for name in ("execute_generated_workflow_query", "run_workflow_query"):
            fn = getattr(t, name)
            src = inspect.getsource(fn)
            self.assertNotIn("@mcp_flowcept", src, f"{name} must not have @mcp_flowcept decorator")

    # ── E1: db_query_mcp_tools.py — no _provenance_ infix ─────────────────
    def test_e1_db_query_mcp_tools_importable_and_names_clean(self):
        from flowcept.agents.mcp.mcp_tools import db_query_mcp_tools
        for name in ("query_tasks", "query_workflows", "get_task_summary", "list_campaigns", "list_agents"):
            self.assertTrue(hasattr(db_query_mcp_tools, name), f"missing {name}")
            self.assertNotIn("provenance", name, f"{name} must not contain 'provenance'")

    # ── E2: in_memory_task_query_mcp_tools.py ─────────────────────────────
    def test_e2_in_memory_task_query_mcp_tools_importable(self):
        from flowcept.agents.mcp.mcp_tools.in_memory_task_query_mcp_tools import (
            run_df_query,
        )
        self.assertTrue(callable(run_df_query))

    # ── E3: in_memory_workflow_query_mcp_tools.py ─────────────────────────
    def test_e3_in_memory_workflow_query_mcp_tools_importable(self):
        from flowcept.agents.mcp.mcp_tools.in_memory_workflow_query_mcp_tools import (
            run_workflow_query,
        )
        self.assertTrue(callable(run_workflow_query))

    # ── E4: session_tools.py + report_tools.py ────────────────────────────
    def test_e4_session_tools_importable(self):
        from flowcept.agents.mcp.mcp_tools import (
            check_liveness,
        )
        self.assertTrue(callable(check_liveness))

    def test_e4_report_tools_importable(self):
        from flowcept.agents.mcp.mcp_tools import generate_workflow_card
        self.assertTrue(callable(generate_workflow_card))

    # ── E5: mcp_prompts.py importable ─────────────────────────────────────
    def test_e5_mcp_prompts_importable(self):
        import flowcept.agents.prompts.mcp_prompts  # noqa: F401
        self.assertTrue(True)

    # ── F1: base_prompts.py — BASE_ROLE + build_*_prompt functions ─────────
    def test_f1_base_prompts_importable(self):
        from flowcept.agents.prompts.base_prompts import (
            BASE_ROLE,
            build_single_task_prompt,
            build_multitask_prompt,
        )
        self.assertIn("provenance", BASE_ROLE.lower())
        self.assertTrue(callable(build_single_task_prompt))
        self.assertTrue(callable(build_multitask_prompt))

    # ── F2: db_query_prompts.py ───────────────────────────────────────────
    def test_f2_db_query_prompts_importable(self):
        from flowcept.agents.prompts.db_query_prompts import build_db_filter_prompt
        self.assertTrue(callable(build_db_filter_prompt))
        result = build_db_filter_prompt("find tasks in error")
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    # ── F3: in_memory_task_query_prompts.py (renamed) ─────────────────────
    def test_f3_in_memory_task_query_prompts_importable(self):
        from flowcept.agents.prompts.in_memory_task_query_prompts import (
            generate_pandas_code_prompt,
        )
        self.assertTrue(callable(generate_pandas_code_prompt))

    # ── F4: in_memory_workflow_query_prompts.py (renamed) ─────────────────
    def test_f4_in_memory_workflow_query_prompts_importable(self):
        from flowcept.agents.prompts.in_memory_workflow_query_prompts import (
            generate_workflow_query_prompt,
            EMPTY_WORKFLOW_MESSAGE,
        )
        self.assertTrue(callable(generate_workflow_query_prompt))
        self.assertIsInstance(EMPTY_WORKFLOW_MESSAGE, str)

    # ── G4: agent_mode setting ────────────────────────────────────────────
    def test_g4_agent_mode_setting_in_configs(self):
        from flowcept.configs import AGENT_MODE
        self.assertIn(AGENT_MODE, ("disabled", "separate", "colocated"))

    # ── G5: chat router accepts thread_id ─────────────────────────────────
    def test_g5_chat_request_has_thread_id(self):
        from flowcept.webservice.routers.chat import ChatRequest
        import inspect
        params = inspect.signature(ChatRequest).parameters
        # thread_id should be declared as a field (even if Optional)
        self.assertIn("thread_id", ChatRequest.model_fields)

    # ── G2-G3: run_chat accepts thread_id ─────────────────────────────────
    def test_g2_run_chat_signature_has_thread_id(self):
        from flowcept.agents.chat_orchestration.chat_orchestrator_service import run_chat
        import inspect
        sig = inspect.signature(run_chat)
        self.assertIn("thread_id", sig.parameters)

    def test_g6_chat_router_forwards_thread_id_to_orchestrator(self):
        from flowcept.webservice.routers import chat as chat_router

        payload = chat_router.ChatRequest(
            messages=[chat_router.ChatMessage(role="user", content="hello")],
            stream=False,
            thread_id="thread-123",
        )

        with (
            patch.object(chat_router, "get_chat_llm", return_value=object()),
            patch.object(chat_router, "run_chat", return_value=iter([{"event": "done"}])) as run_chat_mock,
        ):
            response = chat_router.chat(payload)

        self.assertEqual(response, {"message": "", "tool_trace": [], "cards": []})
        self.assertEqual(run_chat_mock.call_args.kwargs["thread_id"], "thread-123")


class TestLLMRoundTrips(unittest.TestCase):
    """I4: LLM-dependent round-trip tests.  Marked @pytest.mark.llm so CI skips them."""

    def _skip_if_no_llm(self):
        api_key = AGENT.get("api_key", "")
        if not api_key or api_key in ("?", "your-api-key-here", ""):
            FlowceptLogger().warning("Skipping LLM round-trip test: no valid api_key in AGENT settings.")
            self.skipTest("LLM not configured.")

    @pytest.mark.llm
    def test_i4_run_df_query_real_llm(self):
        """run_df_query uses a real LLM to generate pandas code and returns a successful ToolResult."""
        self._skip_if_no_llm()
        import pandas as pd
        from flowcept.agents.data_query_tools.in_memory_task_query_tools import run_df_query
        from flowcept.agents.llm.builders import build_llm_model

        df = pd.DataFrame({
            "activity_id": ["train", "train", "eval"],
            "status": ["finished", "finished", "finished"],
            "telemetry_summary.duration_sec": [10.0, 12.5, 5.0],
        })
        schema = {"activity_id": {"type": "str"}, "status": {"type": "str"}}
        llm = build_llm_model(track_tools=False)
        result = run_df_query(
            query="How many rows are there?",
            df=df,
            schema=schema,
            value_examples={},
            custom_user_guidance=[],
            llm=llm,
        )
        self.assertIn(result.code, (201, 301), f"Expected success code, got {result.code}: {result.result}")

    @pytest.mark.llm
    def test_i4_run_chat_tool_call_round_trip(self):
        """run_chat drives tool calling with a real LLM, yielding tool_call + token + done events."""
        self._skip_if_no_llm()
        if not Flowcept.services_alive():
            FlowceptLogger().warning("Skipping run_chat round-trip: Flowcept services not alive.")
            self.skipTest("Flowcept services not alive.")
        from flowcept.agents.llm.builders import build_llm_model
        from flowcept.agents.chat_orchestration.chat_orchestrator_service import run_chat

        llm = build_llm_model(track_tools=False)
        messages = [{"role": "user", "content": "How many tasks are there in the database?"}]
        events = list(run_chat(llm, messages=messages))
        event_types = [e["event"] for e in events]
        self.assertIn("done", event_types, f"Expected 'done' event, got: {event_types}")
        self.assertTrue(
            any(e in event_types for e in ("token", "error")),
            f"Expected 'token' or 'error' event, got: {event_types}",
        )

    @pytest.mark.llm
    def test_i4_langgraph_thread_memory(self):
        """thread_id enables server-side conversation memory: follow-up question recalls prior answer."""
        self._skip_if_no_llm()
        from flowcept.agents.llm.builders import build_llm_model
        from flowcept.agents.chat_orchestration.chat_orchestrator_service import run_chat

        import uuid
        tid = f"test-thread-{uuid.uuid4()}"
        llm = build_llm_model(track_tools=False)

        # First turn: plant a fact
        events1 = list(run_chat(llm, messages=[{"role": "user", "content": "My lucky number is 7777."}], thread_id=tid))
        types1 = [e["event"] for e in events1]
        self.assertIn("done", types1, f"First turn missing 'done': {types1}")

        # Second turn: recall the fact (only new message; server owns history via MemorySaver)
        events2 = list(run_chat(llm, messages=[{"role": "user", "content": "What is my lucky number?"}], thread_id=tid))
        full_text = " ".join(str(e.get("data", "")) for e in events2 if e["event"] == "token")
        self.assertIn("7777", full_text, f"Expected '7777' in follow-up response, got: {full_text!r}")


class TestProvAgentInstrumentation(unittest.TestCase):
    """Structural tests for PROV-AGENT enum usage.  No live services required."""

    def test_prov_agent_enum_values(self):
        from flowcept.commons.vocabulary import PROV_AGENT

        self.assertEqual(PROV_AGENT.AI_MODEL_INVOCATION.value, "ai_model_invocation")
        self.assertEqual(PROV_AGENT.AGENT_TOOL.value, "agent_tool")

    def test_flowcept_llm_uses_prov_agent_enum_not_bare_string(self):
        import inspect
        from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM

        src = inspect.getsource(FlowceptLLM._our_call)
        self.assertNotIn('"llm_task"', src, "FlowceptLLM must use PROV_AGENT.AI_MODEL_INVOCATION, not bare string")
        self.assertIn("PROV_AGENT.AI_MODEL_INVOCATION", src)

    def test_agent_flowcept_task_default_uses_prov_agent_enum(self):
        import inspect
        import flowcept.instrumentation.flowcept_agent_task as m

        src = inspect.getsource(m.agent_flowcept_task)
        self.assertNotIn('"agent_task"', src, "agent_flowcept_task must use PROV_AGENT.AGENT_TOOL, not bare string")
        self.assertIn("PROV_AGENT.AGENT_TOOL", src)

    def test_context_manager_comparisons_use_prov_agent_enum(self):
        import inspect
        from flowcept.agents.context_manager import FlowceptAgentContextManager

        src = inspect.getsource(FlowceptAgentContextManager.message_handler)
        self.assertNotIn('"llm_task"', src)
        self.assertNotIn('"agent_task"', src)
        self.assertIn("PROV_AGENT", src)

    def test_mcp_db_query_tools_use_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp_tools.db_query_mcp_tools as m

        src = inspect.getsource(m)
        self.assertIn("agent_flowcept_task", src)
        self.assertIn("PROV_AGENT", src)

    def test_report_tools_use_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp_tools.report_tools as m

        src = inspect.getsource(m)
        self.assertIn("agent_flowcept_task", src)

    def test_in_memory_task_query_mcp_tools_use_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp_tools.in_memory_task_query_mcp_tools as m

        src = inspect.getsource(m)
        self.assertIn("agent_flowcept_task", src)

    def test_session_tools_prompt_handler_uses_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp_tools.session_tools as m

        src = inspect.getsource(m)
        self.assertIn("agent_flowcept_task", src)

    def test_format_messages_handles_base_messages(self):
        from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

        msgs = [SystemMessage(content="sys"), HumanMessage(content="hi"), AIMessage(content="hello")]
        result = FlowceptLLM._format_messages(msgs)
        self.assertIn("hi", result)
        self.assertIn("hello", result)
        self.assertIn("sys", result)

    def test_run_chat_wraps_graph_in_flowcept_context(self):
        """Each LangGraph execution is wrapped in a Flowcept context to get its own workflow_id."""
        import inspect
        from flowcept.webservice.services import chat_orchestrator_service as svc

        src = inspect.getsource(svc.run_chat)
        # Must use Flowcept context manager, not manual WorkflowObject
        self.assertIn("langgraph_chat", src)
        self.assertNotIn("WorkflowObject", src)
        self.assertIn("start_persistence=False", src)
        self.assertIn("save_workflow=True", src)

    def test_build_graph_does_not_accept_workflow_id(self):
        """workflow_id is not threaded through _build_graph — Flowcept.current_workflow_id is used instead."""
        import inspect
        from flowcept.webservice.services import chat_orchestrator_service as svc

        sig = inspect.signature(svc._build_graph)
        self.assertNotIn("workflow_id", sig.parameters)
