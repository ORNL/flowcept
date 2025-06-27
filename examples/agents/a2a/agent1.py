import random
from typing import Dict

import uvicorn
from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task
from flowcept.instrumentation.flowcept_task import flowcept_task
from mcp.server.fastmcp import FastMCP

from flowcept.configs import AGENT


@flowcept_task(subtype="call_agent_task")
def agent_task2(**kwargs):
    return


class Agent1ContextManager(BaseAgentContextManager):

    def __init__(self):
        super().__init__()

    def message_handler(self, msg_obj: Dict) -> bool:
        if msg_obj.get('type', '') == 'task':
            subtype = msg_obj.get("subtype", '')
            if subtype == 'agent_task':
                print(msg_obj)
                tool_name = msg_obj["activity_id"]
                generated = msg_obj["generated"]
                if tool_name == 'agent_task1':
                    self.logger.debug(f"Ok, Agent 1 executed agent_task1. Now going to send Message to Agent 2")
                    agent_task2(**generated)
                elif tool_name == "agent_task2":
                    self.logger.debug(f"Ok, Agent 2 executed agent_task2. All good. Its output was: {generated}")
        return True


agent_controller = Agent1ContextManager()
mcp = FastMCP("Agent1", require_session=True, lifespan=agent_controller.lifespan)


@mcp.tool()
@agent_flowcept_task  # Must be in this order. @mcp.tool then @flowcept_task
def agent_task1(campaign_id=None):
    return {
        "msg": "I'm agent 1 and I wish to talk to agent 2!",
        "data": random.randint(0, 350)
    }

def main():
    """
    Start the MCP server.
    """
    uvicorn.run(
        mcp.streamable_http_app, host=AGENT.get("mcp_host", "0.0.0.0"), port=AGENT.get("mcp_port", 8000), lifespan="on"
    )


if __name__ == "__main__":
    main()
