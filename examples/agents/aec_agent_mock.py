import json
import os
from typing import Dict, List
import textwrap

import uvicorn
from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from flowcept.flowceptor.consumers.agent.client_agent import run_tool
from flowcept.instrumentation.flowcept_task import flowcept_task
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


class AdamantineAeCContextManager(BaseAgentContextManager):

    def __init__(self):
        super().__init__()

    def message_handler(self, msg_obj: Dict) -> bool:
        if msg_obj.get('type', '') == 'task':
            tag = msg_obj.get("tags", [''])[0]
            if tag == 'run_tool':
                print(msg_obj)
                tool_name = msg_obj["activity_id"]
                tool_args = msg_obj.get("used", {})
                self.logger.debug(f"Going to run {tool_name}, {tool_args}")
                run_tool(tool_name, kwargs=tool_args)
            elif tag == 'tool_result':
                print('Tool result', msg_obj["activity_id"])
            if msg_obj.get("subtype", '') == "llm_query":
                print("Msg from agent.")
                #
                # msg_output = msg_obj.get("generated", {})["response"]
                #
                # simulation_output = simulate_layer(self._layers_count, msg_output)
                #
                # run_tool_async("ask_agent", simulation_output)

        else:
            print(f"We got a msg with different type: {msg_obj.get("type", None)}")
        return True


agent_controller = AdamantineAeCContextManager()
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
@flowcept_task(tags=["tool_result"])  # Must be in this order. @mcp.tool then @flowcept_task
def generate_options_set(layer: int, planned_controls, number_of_options=4):
    # search the whole history of options, scores, and choices
    import random
    dwell_arr = list(range(10, 121, 5))

    control_options = []
    for k in range(number_of_options):
        control_options.append({
            "power": random.randint(0, 350),
            "dwell_0": dwell_arr[random.randint(0, len(dwell_arr) - 1)],
            "dwell_1": dwell_arr[random.randint(0, len(dwell_arr) - 1)],
        })
    return {"control_options": control_options}


@mcp.tool()
@flowcept_task(tags=["tool_result"])  # Must be in this order. @mcp.tool then @flowcept_task
def choose_option(l2_error: List[float], planned_controls):
    # search the whole history of options, scores, and choice
    import numpy as np
    minimum_error_ix = int(np.argmin(l2_error))
    return {"option": minimum_error_ix, "reason": "argmin"}
#
# @mcp.tool()
# def ask_agent(layer: int = None) -> str:
#     """
#     Return the latest task(s) as a JSON string.
#     """
#     ctx = mcp.get_context()
#     tasks = ctx.request_context.lifespan_context.tasks
#     if not tasks:
#         return "No tasks available."
#     if n is None:
#         return json.dumps(tasks[-1])
#     return json.dumps(tasks[-n])



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

    layer = task_data.get('used').get('layer_number', 0)
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
    uvicorn.run(
        mcp.streamable_http_app, host=AGENT.get("mcp_host", "0.0.0.0"), port=AGENT.get("mcp_port", 8000), lifespan="on"
    )


if __name__ == "__main__":
    main()
