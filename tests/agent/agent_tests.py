import json
import unittest
from uuid import uuid4

from flowcept.agents import prompt_handler, ToolResult
from flowcept.agents.agent_client import run_tool
from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
from flowcept.configs import AGENT

AGENT_ENABLED = AGENT.get("enabled", False)

@unittest.skipIf(not AGENT_ENABLED, "Agent is disabled")
class TestAgent(unittest.TestCase):


    def test_tool_call(self):
        resp = run_tool(tool_name=prompt_handler, kwargs={"message": "show all tasks"})[0]

        tool_result = ToolResult(**json.loads(resp))
        with open("/tmp/test.md", "w") as f:
            f.write(tool_result.result["result_df_markdown"])
