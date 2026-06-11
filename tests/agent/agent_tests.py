import json
import os
import tempfile
from time import sleep
import unittest
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

        from flowcept.agents import flowcept_agent as agent_module

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

        from flowcept.agents import flowcept_agent as agent_module
        from flowcept.agents.agent_client import run_tool
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
            resp = run_tool("query_provenance_tasks", kwargs={"filter": {"workflow_id": workflow_id}})[0]
            tool_result = ToolResult(**json.loads(resp))
            self.assertIn(tool_result.code, {201, 301})
            items = tool_result.result["items"]
            self.assertTrue(any(t["activity_id"] == "mcp_seed" for t in items))

            resp = run_tool("list_provenance_campaigns", kwargs={})[0]
            tool_result = ToolResult(**json.loads(resp))
            self.assertIn(tool_result.code, {201, 301})
            self.assertTrue(any(c["campaign_id"] == campaign_id for c in tool_result.result["items"]))
        finally:
            agent.stop()
            if DocumentDBDAO._instance is not None:
                DocumentDBDAO._instance.close()


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
        from flowcept.agents.prompts import in_memory_query_prompts as t

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
        from flowcept.agents.prompts import in_memory_query_prompts as t

        dummy_ctx = self._DummyContext(df=pd.DataFrame(), schema={}, value_examples={}, custom_user_guidance=[])
        with patch.object(t.mcp_flowcept, "get_context", return_value=dummy_ctx):
            prompt_text = t.build_df_query_prompt(query="anything")

        self.assertEqual(prompt_text, "Current df is empty or null.")

    def test_execute_generated_df_code_runs_against_current_df(self):
        from flowcept.agents.tools.in_memory_queries import in_memory_queries_tools as t

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
        from flowcept.agents.tools import general_tools as g

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

        from flowcept.agents import flowcept_agent as agent_module

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
