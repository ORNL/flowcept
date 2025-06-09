import json
import os
from typing import Dict
import textwrap

import uvicorn
from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

from flowcept.configs import AGENT
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.agents.agents_utils import convert_mcp_to_langchain
from flowcept.flowceptor.adapters.agents.flowcept_llm_prov_capture import invoke_llm, add_preamble_to_response
from flowcept.flowceptor.adapters.agents.prompts import get_question_prompt,  BASE_SINGLETASK_PROMPT
from flowcept.commons.utils import get_utc_now

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")

agent_controller = BaseAgentContextManager()
mcp = FastMCP("AnC_Agent_mock", require_session=True, lifespan=agent_controller.lifespan)


#################################################
# PROMPTS
#################################################

@mcp.prompt()
def single_task_used_generated_prompt(task_data: Dict, question: str) -> list[base.Message]:
    """
    Generates a prompt to ask about one particular task.
    """
    msgs = BASE_SINGLETASK_PROMPT.copy()
    msgs.append(get_question_prompt(question))
    msgs.append(base.UserMessage(f"This is the task object I need you to focus on: \n {task_data}\n"))
    return msgs


@mcp.prompt()
def adamantine_prompt(layer: int, simulation_output: Dict, question: str) -> list[base.Message]:
    control_options = simulation_output.get("control_options")
    l2_error = simulation_output.get("l2_error")

    control_options_str = ""
    for o in range(len(control_options)):
        control_options_str += f"Option {o + 1}: {control_options[o]}\n"

    l2_error_str = ""
    for o in range(len(l2_error)):
        l2_error_str += f"Option {o + 1}: {l2_error[o]}\n"

    prompt = textwrap.dedent(f"""\
    SUMMARY OF CURRENT STATE: Currently, the printer is printing layer {layer}. You need to make a control decision for layer {layer + 2}. It is currently {get_utc_now()}.

    CONTROL OPTIONS: 
    {control_options_str}

    AUTOMATED ANALYSIS FROM SIMULATIONS:
    Full volume L2 error (lower is better)

    {l2_error_str}
    """).strip()

    return [
        base.UserMessage(prompt),
        base.UserMessage(f"Based on this provided information, here is the question: {question}")
    ]


#################################################
# TOOLS
#################################################

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


@mcp.tool()
def adamantine_ask_about_latest_iteration(question) -> str:
    ctx = mcp.get_context()
    tasks = ctx.request_context.lifespan_context.tasks
    if not tasks:
        return "No tasks available."
    task_data = tasks[-1]

    layer = task_data.get('used').get('layer_number')
    simulation_output = task_data.get('generated')

    messages = adamantine_prompt(layer, simulation_output, question)

    langchain_messages = convert_mcp_to_langchain(messages)

    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp, task_data)
    return result


def main():
    """
    Start the MCP server.
    """
    f = Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False).start()
    f.logger.info(f"This section's workflow_id={Flowcept.current_workflow_id}")
    setattr(mcp, "workflow_id", f.current_workflow_id)
    uvicorn.run(mcp.streamable_http_app, host="0.0.0.0", port=8000, lifespan="on")


if __name__ == "__main__":
    main()
