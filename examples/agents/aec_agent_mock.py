import json
from typing import Dict, List

import numpy as np
import uvicorn
from flowcept.instrumentation.flowcept_agent_task import agent_flowcept_task
from mcp.server.fastmcp import FastMCP

from flowcept.configs import AGENT
from flowcept.agents.agents_utils import build_llm_model

from examples.agents.aec_agent_context_manager import AdamantineAeCContextManager
from examples.agents.aec_prompts import choose_option_prompt, generate_options_set_prompt


agent_controller = AdamantineAeCContextManager()
mcp = FastMCP("AnC_Agent_mock", require_session=True, lifespan=agent_controller.lifespan)



#################################################
# TOOLS
#################################################


@mcp.tool()
@agent_flowcept_task  # Must be in this order. @mcp.tool then @flowcept_task
def generate_options_set(layer: int, planned_controls, number_of_options=4, campaign_id=None):
    llm = build_llm_model()
    ctx = mcp.get_context()
    history = ctx.request_context.lifespan_context.history
    messages = generate_options_set_prompt(layer, planned_controls, history, number_of_options)
    response = llm.invoke(messages)

    try:
        control_options = json.loads(response)
    except Exception as e:
        raise Exception(f"Could not parse json in generate_options_set. Error {e}. Likely an LLM output problem. "
                        f"This is the JSON we tried to parse: {response}")

    assert len(control_options) == number_of_options
    return {"control_options": control_options}


@mcp.tool()
@agent_flowcept_task  # Must be in this order. @mcp.tool then @flowcept_task
def choose_option(scores: Dict, planned_controls: List[Dict], campaign_id: str=None):
    llm = build_llm_model()
    ctx = mcp.get_context()
    history = ctx.request_context.lifespan_context.history
    messages = choose_option_prompt(scores, planned_controls, history)
    response = llm.invoke(messages)
    try:
        result = json.loads(response)
    except Exception as e:
        raise Exception(f"Could not parse json in choose_option. Error {e}. Likely an LLM output problem. "
                        f"This is the JSON we tried to parse: {response}")

    human_option = int(np.argmin(scores["scores"]))

    result["human_option"] = human_option
    result["attention"] = True if human_option != result["option"] else False

    return result


@mcp.tool()
def get_latest(n: int = None) -> str:
    """
    Return the latest task(s) as a JSON string.
    """
    ctx = mcp.get_context()
    tasks = ctx.request_context.lifespan_context.tasks
    if not tasks:
        return "No tasks available."
    if n is None:
        return json.dumps(tasks[-1])
    return json.dumps(tasks[-n])


@mcp.tool()
def check_liveness() -> str:
    """
    Check if the agent is running.
    """

    return f"I'm {mcp.name} and I'm ready!"


@mcp.tool()
def check_llm() -> str:
    """
    Check if the agent can talk to the LLM service.
    """
    llm = build_llm_model()
    response = llm.invoke("Hello, are you there?")
    return response


def main():
    """
    Start the MCP server.
    """
    uvicorn.run(
        mcp.streamable_http_app, host=AGENT.get("mcp_host", "0.0.0.0"), port=AGENT.get("mcp_port", 8000), lifespan="on"
    )


if __name__ == "__main__":
    main()
