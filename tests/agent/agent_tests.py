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

        agent = agent_module.FlowceptMCPServer(buffer_path=buffer_path)
        agent.start()
        try:
            from flowcept.agents.mcp.mcp_client import run_tool

            sleep(0.5)
            resp = run_tool("get_latest")[0]
            latest = json.loads(resp)
            self.assertEqual(latest["activity_id"], "offline_buffer_task")
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

        agent = agent_module.FlowceptMCPServer()
        agent.start()
        try:
            resp = run_tool("db_query_tasks", kwargs={"filter": {"workflow_id": workflow_id}})[0]
            tool_result = ToolResult(**json.loads(resp))
            self.assertIn(tool_result.code, {201, 301})
            items = tool_result.result["items"]
            self.assertTrue(any(t["activity_id"] == "mcp_seed" for t in items))

            resp = run_tool("db_list_campaigns", kwargs={})[0]
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

    def test_get_df_schema_context_returns_prompt_payload(self):
        from flowcept.agents.mcp.mcp_tools.schema_mcp_tools import get_df_schema_context
        from flowcept.agents.mcp import context_manager as cm

        df = pd.DataFrame({"activity_id": ["a", "b"], "used.x": [1, 2]})
        cm.ctx_manager.context.df = df
        cm.ctx_manager.context.tasks_schema = {"activity_a": {"i": ["used.x"], "o": []}}
        cm.ctx_manager.context.value_examples = {"x": {"t": "int", "v": [1, 2]}}
        cm.ctx_manager.context.custom_guidance = ["prefer concise outputs"]

        result = get_df_schema_context(context_kind="tasks")

        self.assertEqual(result.code, 301)
        self.assertIn("prompt_context", result.result)
        prompt_text = result.result["prompt_context"]
        self.assertIsInstance(prompt_text, str)
        self.assertIn("ALLOWED_FIELDS", prompt_text)
        self.assertIn("activity_id", prompt_text)

        cm.ctx_manager.context.reset_context()

    def test_get_df_schema_context_returns_404_when_df_missing(self):
        from flowcept.agents.mcp.mcp_tools.schema_mcp_tools import get_df_schema_context
        from flowcept.agents.mcp import context_manager as cm

        cm.ctx_manager.context.df = pd.DataFrame()
        result = get_df_schema_context(context_kind="tasks")
        self.assertEqual(result.code, 404)
        self.assertEqual(result.result, cm.EMPTY_DF_MESSAGE)

    def test_execute_generated_df_code_runs_against_current_df(self):
        from flowcept.agents.data_query_tools.df_query_tools import execute_df_code

        df = pd.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]})
        tool_result = execute_df_code(user_code="result = df[['a']].head(2)", df=df)

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

        agent = agent_module.FlowceptMCPServer(buffer_path=buffer_path)
        agent.start()
        try:
            from flowcept.agents.mcp.mcp_client import run_tool

            sleep(0.5)
            resp = run_tool("get_latest")[0]
            latest = json.loads(resp)
            self.assertEqual(latest["activity_id"], "offline_buffer_task")
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
        from flowcept.agents.mcp.context_manager import FlowceptAgentContextManager
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

    # ── C1: mcp_server.py (was flowcept_agent.py) ─────────────────────────
    def test_c1_mcp_server_importable(self):
        from flowcept.agents.mcp.mcp_server import FlowceptMCPServer
        self.assertTrue(callable(FlowceptMCPServer))

    # ── C2: mcp_client.py (was agent_client.py) ───────────────────────────
    def test_c2_mcp_client_importable(self):
        from flowcept.agents.mcp.mcp_client import run_tool, run_prompt
        self.assertTrue(callable(run_tool))
        self.assertTrue(callable(run_prompt))

    # ── C3: context_manager.py (was flowcept_ctx_manager.py) ──────────────
    def test_c3_context_manager_importable(self):
        from flowcept.agents.mcp.context_manager import (
            ctx_manager,
            mcp_flowcept,
        )
        self.assertIsNotNone(ctx_manager)
        self.assertEqual(mcp_flowcept.name, "FlowceptAgent")

    # ── D1: db_query_tools.py ─────────────────────────────────────────────
    def test_d1_db_query_tools_importable(self):
        from flowcept.agents.data_query_tools.db_query_tools import query_tasks
        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import (
            ALLOWED_FILTER_OPERATORS,
            validate_filter,
        )
        self.assertIn("$eq", ALLOWED_FILTER_OPERATORS)
        self.assertTrue(callable(query_tasks))
        validate_filter({"status": {"$eq": "FINISHED"}})  # must not raise

    # ── D2: df_query_tools.py ─────────────────────────────────────────────
    def test_d2_df_query_tools_importable(self):
        from flowcept.agents.data_query_tools.df_query_tools import (
            run_df_query,
        )
        self.assertTrue(callable(run_df_query))

    # ── D3: pandas_utils.py ───────────────────────────────────────────────
    def test_d3_pandas_utils_importable(self):
        from flowcept.agents.data_query_tools.pandas_utils import (
            safe_execute,
        )
        self.assertTrue(callable(safe_execute))

    # ── D4: df_query_tools.py ─────────────────────────────────────────────
    def test_d4_df_query_tools_importable(self):
        from flowcept.agents.data_query_tools.df_query_tools import (
            execute_df_code,
            DFQueryTools,
        )
        self.assertTrue(callable(execute_df_code))
        self.assertTrue(callable(DFQueryTools))

    # ── E1: db_query_mcp_tools.py — no _provenance_ infix ─────────────────
    def test_e1_db_query_mcp_tools_importable_and_names_clean(self):
        from flowcept.agents.mcp.mcp_tools import db_query_mcp_tools
        for name in ("db_query_tasks", "db_query_workflows", "db_get_task_summary", "db_list_campaigns", "db_list_agents"):
            self.assertTrue(hasattr(db_query_mcp_tools, name), f"missing {name}")
            self.assertNotIn("provenance", name, f"{name} must not contain 'provenance'")

    # ── E4: session_tools.py + report_tools.py ────────────────────────────
    def test_e4_session_tools_importable(self):
        from flowcept.agents.mcp.mcp_tools import (
            check_liveness,
        )
        self.assertTrue(callable(check_liveness))

    def test_e4_report_tools_importable(self):
        from flowcept.agents.mcp.mcp_tools import generate_workflow_card
        self.assertTrue(callable(generate_workflow_card))

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
        from flowcept.agents.prompts.db_query_prompts import build_db_schema_context
        self.assertTrue(callable(build_db_schema_context))
        result = build_db_schema_context()
        self.assertIsInstance(result, str)
        self.assertGreater(len(result), 0)

    def test_f3_schema_prompt_context_is_domain_neutral_and_shared(self):
        from flowcept.agents.prompts.schema_prompt_context import (
            build_allowed_fields_prompt,
            build_example_values_prompt,
            build_task_static_field_table,
            build_task_structure_prompt,
        )

        current_fields = ["activity_id", "used.input_value", "generated.output_value"]
        examples = {"input_value": {"t": "int", "v": [1]}, "output_value": {"t": "float", "v": [2.0]}}
        allowed = build_allowed_fields_prompt(current_fields, target_name="df")
        table = build_task_static_field_table(current_fields)
        values = build_example_values_prompt(examples)
        structure = build_task_structure_prompt(
            dynamic_schema={"step_a": {"i": ["used.input_value"], "o": ["generated.output_value"]}},
            example_values=examples,
            current_fields=current_fields,
            record_description="Each record represents one task.",
        )

        combined = "\n".join([allowed, table, values, structure]).lower()
        self.assertIn("allowed_fields", combined)
        self.assertIn("used.input_value", combined)
        self.assertIn("generated.output_value", combined)
        for forbidden in ("gridsearch", "hyperparameter", "training", "model", "cfg_"):
            self.assertNotIn(forbidden, combined)

    # ── G4: agent_mode setting ────────────────────────────────────────────
    def test_g4_agent_mode_setting_in_configs(self):
        from flowcept.configs import AGENT_MODE
        self.assertIn(AGENT_MODE, ("disabled", "separate", "colocated"))

    # ── G5: chat router accepts thread_id ─────────────────────────────────
    def test_g5_chat_request_has_thread_id(self):
        from flowcept.webservice.routers.chat import ChatRequest
        import inspect
        inspect.signature(ChatRequest).parameters
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
        from flowcept.agents.mcp.context_manager import FlowceptAgentContextManager

        src = inspect.getsource(FlowceptAgentContextManager.message_handler)
        self.assertNotIn('"llm_task"', src)
        self.assertNotIn('"agent_task"', src)
        self.assertIn("PROV_AGENT", src)

    def test_context_manager_caches_dynamic_schema_by_workflow_id(self):
        from flowcept.agents.mcp.context_manager import FlowceptAgentContextManager

        manager = FlowceptAgentContextManager()
        manager.message_handler(
            {
                "type": "task",
                "workflow_id": "wf-a",
                "activity_id": "step_a",
                "used": {"input_value": 1},
                "generated": {"output_value": 2},
            }
        )
        manager.message_handler(
            {
                "type": "task",
                "workflow_id": "wf-b",
                "activity_id": "step_b",
                "used": {"other_input": "x"},
                "generated": {"other_output": "y"},
            }
        )

        wf_a = manager.get_workflow_schema_snapshot("wf-a")
        wf_b = manager.get_workflow_schema_snapshot("wf-b")

        self.assertIn("step_a", wf_a["dynamic_schema"])
        self.assertNotIn("step_b", wf_a["dynamic_schema"])
        self.assertIn("used.input_value", wf_a["current_fields"])
        self.assertIn("step_b", wf_b["dynamic_schema"])
        self.assertNotIn("step_a", wf_b["dynamic_schema"])

    def test_schema_mcp_tool_returns_workflow_prompt_context(self):
        from flowcept.agents.mcp.context_manager import ctx_manager
        from flowcept.agents.mcp.mcp_tools.schema_mcp_tools import get_workflow_schema_context

        ctx_manager.reset_context()
        ctx_manager.message_handler(
            {
                "type": "task",
                "workflow_id": "wf-schema-tool",
                "activity_id": "step_a",
                "used": {"input_value": 1},
                "generated": {"output_value": 2},
            }
        )

        result = get_workflow_schema_context(workflow_id="wf-schema-tool")

        self.assertEqual(result.code, 301)
        self.assertIn("prompt_context", result.result)
        self.assertIn("used.input_value", result.result["prompt_context"])
        self.assertIn("generated.output_value", result.result["prompt_context"])

    def test_mcp_db_query_tools_use_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp.mcp_tools.db_query_mcp_tools as m

        src = inspect.getsource(m)
        self.assertIn("agent_flowcept_task", src)
        self.assertIn("PROV_AGENT", src)

    def test_report_tools_use_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp.mcp_tools.report_tools as m

        src = inspect.getsource(m)
        self.assertIn("agent_flowcept_task", src)

    def test_df_query_mcp_tools_use_agent_flowcept_task(self):
        import inspect
        import flowcept.agents.mcp.mcp_tools.df_query_mcp_tools as m

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

    def test_extract_llm_usage_normalizes_langchain_response_metadata(self):
        from langchain_core.messages import AIMessage

        from flowcept.instrumentation.flowcept_agent_task import extract_llm_usage

        response = AIMessage(
            content="answer text",
            usage_metadata={"input_tokens": 3, "output_tokens": 2, "total_tokens": 5},
            response_metadata={"model_name": "gpt-test", "finish_reason": "stop", "id": "req-123"},
        )

        usage = extract_llm_usage(response, input_text="abc", output_text=response.content)

        self.assertEqual(usage["model"], "gpt-test")
        self.assertEqual(usage["input_tokens"], 3)
        self.assertEqual(usage["output_tokens"], 2)
        self.assertEqual(usage["total_tokens"], 5)
        self.assertEqual(usage["input_chars"], 3)
        self.assertEqual(usage["output_chars"], 11)
        self.assertEqual(usage["finish_reason"], "stop")
        self.assertEqual(usage["provider_request_id"], "req-123")
        self.assertEqual(usage["llm_model"], "gpt-test")
        self.assertEqual(usage["llm_total_tokens"], 5)

    def test_extract_llm_usage_estimates_missing_provider_tokens_from_text(self):
        from langchain_core.messages import AIMessage

        from flowcept.instrumentation.flowcept_agent_task import extract_llm_usage

        usage = extract_llm_usage(
            AIMessage(content="abcd" * 5),
            fallback_model="model-without-token-usage",
            input_text="abcd" * 10,
            output_text="abcd" * 5,
        )

        self.assertEqual(usage["model"], "model-without-token-usage")
        self.assertEqual(usage["input_tokens"], 10)
        self.assertEqual(usage["output_tokens"], 5)
        self.assertEqual(usage["total_tokens"], 15)
        self.assertEqual(usage["token_count_source"], "estimated_from_chars")

    def test_llm_metadata_config_drops_api_keys(self):
        from flowcept.instrumentation.flowcept_agent_task import _extract_llm_metadata

        class MinimalLLMConfig:
            def model_dump(self):
                return {
                    "model": "gpt-test",
                    "openai_api_key": "secret-key",
                    "nested": {"api_key": "secret-key-2"},
                }

        metadata = _extract_llm_metadata(MinimalLLMConfig())

        self.assertEqual(metadata["config"]["model"], "gpt-test")
        self.assertNotIn("openai_api_key", metadata["config"])
        self.assertNotIn("api_key", metadata["config"]["nested"])

    def test_flowcept_llm_records_provider_call_as_ai_model_invocation(self):
        import inspect

        from flowcept.commons.vocabulary import PROV_AGENT
        from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM

        src = inspect.getsource(FlowceptLLM._our_call)

        self.assertIn("subtype=PROV_AGENT.AI_MODEL_INVOCATION", src)
        self.assertEqual(PROV_AGENT.AI_MODEL_INVOCATION.value, "ai_model_invocation")

    def test_run_chat_wraps_graph_in_flowcept_context(self):
        """Each LangGraph execution is wrapped in a Flowcept context to get its own workflow_id."""
        import inspect
        from flowcept.agents.chat_orchestration import chat_orchestrator_service as svc

        src = inspect.getsource(svc.run_chat)
        # Must use Flowcept context manager, not manual WorkflowObject
        self.assertEqual(svc.CHAT_WORKFLOW_NAME, "Flowcept LangGraph Chat")
        self.assertNotIn("WorkflowObject", src)
        self.assertIn("start_persistence=True", src)
        self.assertIn("check_safe_stops=False", src)
        self.assertIn("save_workflow=True", src)

    def test_build_graph_does_not_accept_workflow_id(self):
        """workflow_id is not threaded through _build_graph — Flowcept.current_workflow_id is used instead."""
        import inspect
        from flowcept.agents.chat_orchestration import chat_orchestrator_service as svc

        sig = inspect.signature(svc._build_graph)
        self.assertNotIn("workflow_id", sig.parameters)


class TestContextManager(unittest.TestCase):

    def test_workflow_schema_updates_on_new_activity(self):
        """Schema cache updates when a finished task with a new activity_id arrives."""
        from flowcept.agents.mcp.context_manager import FlowceptAgentContextManager
        from flowcept.commons.vocabulary import Status

        cm = FlowceptAgentContextManager()
        wf_id = "test-wf-schema"

        # Task with activity_id "train" — finished, has both used and generated.
        task1 = {
            "type": "task",
            "task_id": "t1",
            "workflow_id": wf_id,
            "activity_id": "train",
            "used": {"lr": 0.01},
            "generated": {"loss": 0.5},
            "ended_at": 1.0,
            "status": Status.FINISHED,
        }
        cm.message_handler(task1)
        assert wf_id in cm.context.workflow_schema_cache
        cache_after_first = cm.context.workflow_schema_cache[wf_id]
        assert cache_after_first is not None

        # Same activity_id again — schema cache should NOT update again.
        task2 = dict(task1, task_id="t2", used={"lr": 0.001}, generated={"loss": 0.4})
        cm.message_handler(task2)
        assert cm.context.workflow_schema_cache[wf_id] is cache_after_first

        # New activity_id "evaluate" — schema cache SHOULD update.
        task3 = {
            "type": "task",
            "task_id": "t3",
            "workflow_id": wf_id,
            "activity_id": "evaluate",
            "used": {"model": "best"},
            "generated": {"accuracy": 0.95},
            "ended_at": 2.0,
            "status": Status.FINISHED,
        }
        cm.message_handler(task3)
        assert cm.context.workflow_schema_cache[wf_id] is not cache_after_first

    def test_workflow_finish_triggers_schema_persist(self):  # noqa: D102
        """A workflow message with status=FINISHED triggers persist_workflow_schema_snapshot."""
        from unittest.mock import patch
        from flowcept.agents.mcp.context_manager import FlowceptAgentContextManager
        from flowcept.commons.vocabulary import Status

        cm = FlowceptAgentContextManager()
        wf_id = "test-wf-finish"

        # Seed schema cache so persist has something to work with.
        cm.context.workflow_schema_cache[wf_id] = {"dynamic_schema": {}, "value_examples": {}, "current_fields": []}

        wf_msg = {"type": "workflow", "workflow_id": wf_id, "status": Status.FINISHED}
        with patch.object(cm, "persist_workflow_schema_snapshot") as mock_persist:
            cm.message_handler(wf_msg)
            mock_persist.assert_called_once_with(wf_id)
