import json
import os
from typing import Dict, List

import numpy as np
import uvicorn
from flowcept.instrumentation.agent_flowcept_task import agent_flowcept_task
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

from flowcept.configs import AGENT
from flowcept.flowceptor.adapters.agents.agents_utils import convert_mcp_to_langchain, build_llm_model, \
    tuples_to_langchain_messages
from flowcept.flowceptor.adapters.agents.flowcept_llm_prov_capture import invoke_llm, add_preamble_to_response

from examples.agents.aec_agent_context_manager import AdamantineAeCContextManager
from examples.agents.aec_prompts import choose_option_prompt, generate_options_set_prompt

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")


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
    langchain_messages = tuples_to_langchain_messages(messages)
    response = llm.invoke(langchain_messages)
    control_options = json.loads(response) # TODO better error handling
    assert len(control_options) == number_of_options
    return {"control_options": control_options, "response": response, "prompt": langchain_messages, "llm": llm}


@mcp.tool()
@agent_flowcept_task  # Must be in this order. @mcp.tool then @flowcept_task
def choose_option(scores: Dict, planned_controls: List[Dict], campaign_id: str=None):
    llm = build_llm_model()
    ctx = mcp.get_context()
    history = ctx.request_context.lifespan_context.history
    messages = choose_option_prompt(scores, planned_controls, history)
    langchain_messages = tuples_to_langchain_messages(messages)
    response = llm.invoke(langchain_messages)
    result = json.loads(response)

    human_option = int(np.argmin(scores["scores"]))

    result["human_option"] = human_option
    result["attention"] = True if human_option != result["option"] else False

    # Flowcept things:
    result["response"] = response
    result["prompt"] = langchain_messages
    result["llm"] = llm

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

    messages = [base.UserMessage(f"Hi, are you working properly?")]

    langchain_messages = convert_mcp_to_langchain(messages)
    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp)

    return result


def main():
    """
    Start the MCP server.
    """
    uvicorn.run(
        mcp.streamable_http_app, host=AGENT.get("mcp_host", "0.0.0.0"), port=AGENT.get("mcp_port", 8000), lifespan="on"
    )


if __name__ == "__main__":
    main()
