import json
import os
import tempfile
from time import sleep
import unittest

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
