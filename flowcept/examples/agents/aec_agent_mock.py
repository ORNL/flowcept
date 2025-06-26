import json
import os
import sys
from typing import Dict, List

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import uvicorn
from flowcept.instrumentation.agent_flowcept_task import agent_flowcept_task
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base
import pathlib
from flowcept.configs import AGENT
from flowcept.flowceptor.adapters.agents.agents_utils import convert_mcp_to_langchain, build_llm_model, tuples_to_langchain_messages
from flowcept.flowceptor.adapters.agents.flowcept_llm_prov_capture import invoke_llm, add_preamble_to_response
from examples.agents.aec_prompts import choose_option_prompt, generate_options_set_prompt
from examples.agents.aec_agent_context_manager import AdamantineAeCContextManager
from langchain_openai import ChatOpenAI 

# Add manufacturing_agent to path to allow bridge import
MANUFACTURING_AGENT_SRC_PATH = (
    pathlib.Path(__file__).resolve().parents[3]
    / "manufacturing-agent"
    / "manufacturing_agent"
    / "src"
)
sys.path.append(str(MANUFACTURING_AGENT_SRC_PATH))

# Load the .env file from the manufacturing_agent directory
from dotenv import load_dotenv
dotenv_path = MANUFACTURING_AGENT_SRC_PATH / "manufacturing_agent" / ".env"
if dotenv_path.is_file():
    load_dotenv(dotenv_path=dotenv_path)
    print(f"Loaded environment variables from {dotenv_path}")
else:
    print(f"Could not find .env file at {dotenv_path}")


from manufacturing_agent.crew import ManufacturingAgentCrew  
from threading import Lock

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")

# Lightweight per-campaign session manager
class _CrewSession:
    """Encapsulates a CrewAI instance and per-campaign cached data."""

    def __init__(self, campaign_id: str | None):
        self.campaign_id = campaign_id or "default"

        # Instantiate the LLM for CrewAI
        try:
            model_name = AGENT.get("openai_model", "gpt-4o")
            llm = ChatOpenAI(model=model_name)
        except Exception as exc:
            raise RuntimeError(
                "Failed to initialise ChatOpenAI for CrewAI session. Ensure langchain-openai is installed and OPENAI_API_KEY set."
            ) from exc

        self._llm = llm  # Keep reference for provenance

        # Buffer to capture prompt messages emitted at each agent step
        self._prompt_buffer: list = []

        def _step_cb(step_output):
            # TODO: Still need to work on this. 
            """
            Note from Miaosen: Unfortunately the exact class of *step_output* 
            can vary across CrewAI versions (AgentAction, AgentFinish, ToolResult, …).  
            The only stable signal we rely on is the presence of a `messages`
            attribute containing the LangChain prompt list sent to the LLM.
            """

            msgs = getattr(step_output, "messages", None)
            if msgs:
                # .messages can be a single message or list; coerce to list
                if not isinstance(msgs, list):
                    msgs = [msgs]
                self._prompt_buffer.extend(msgs)
            print(f"Prompt messages: {self._prompt_buffer}")

        crew_def = ManufacturingAgentCrew(llm=llm)
        self._crew = crew_def.crew()
        # Register the callback after construction (Crew constructor supports attribute)
        setattr(self._crew, "step_callback", _step_cb)

        self._lock = Lock()

    # Public helper used by choose_option tool
    def decide_option(self, layer: int, planned_controls, scores, campaign_id):
        """Run CrewAI once and return best index & reasoning."""

        crew_inputs = {
            "layer_number": layer,
            "planned_controls": planned_controls,
            "scores": scores,
            "campaign_id": campaign_id,
        }

        # Run sequentially under a lock for thread-safety (FastMCP can be multi-threaded)
        with self._lock:
            self._prompt_buffer.clear()
            raw_result = self._crew.kickoff(inputs=crew_inputs)

        # The CrewOutput object is not JSON-serializable; capture a safe string.
        safe_raw_text = str(raw_result.raw) if hasattr(raw_result, "raw") else str(raw_result)

        best_index = None
        explanation = ""
        try:
            import json as _json
            # CrewOutput.raw is json string from output_task
            decision_data = _json.loads(raw_result.raw)
            best_index = decision_data.get("best_option")
            explanation = decision_data.get("reasoning", "")
        except Exception as exc:
            explanation = f"Could not parse CrewAI output: {exc}. Raw: {raw_result.raw}"

        if best_index is None:
            best_index = int(min(range(len(scores["scores"])), key=scores["scores"].__getitem__))

        # Capture prompt messages collected during this kickoff
        prompt_msgs = list(self._prompt_buffer)

        # Return decision dict
        return {
            "best_index": best_index,
            "reasoning": explanation or "Decision by CrewAI",
            "raw_text": safe_raw_text,
            "prompt_msgs": prompt_msgs,
        }



# Global registry of sessions
_SESSIONS = {}


def _get_session(campaign_id: str | None):
    key = campaign_id or "default"
    if key not in _SESSIONS:
        _SESSIONS[key] = _CrewSession(key)
    return _SESSIONS[key]


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
    # print(f"Generated {control_options} options for layer {layer}")
    return {"control_options": control_options, "response": response, "prompt": langchain_messages, "llm": llm}


@mcp.tool()
@agent_flowcept_task  # Must be in this order. @mcp.tool then @flowcept_task
def choose_option(scores: Dict, planned_controls: List[Dict], campaign_id: str=None):
    sess = _get_session(campaign_id)
    decision = sess.decide_option(scores.get("layer", 0), planned_controls, scores, campaign_id)

    human_option = int(np.argmin(scores["scores"])) if "scores" in scores else None

    crew_prompt_msgs = decision.get("prompt_msgs")

    result = {
        "option": decision["best_index"],
        "explanation": decision["reasoning"],
        "label": "CrewAI",
        "human_option": human_option,
        "attention": (human_option is not None and decision["best_index"] != human_option),
        "response": decision["raw_text"],
        "prompt": crew_prompt_msgs,
        "llm": sess._llm,
    }
    # llm = build_llm_model()
    # ctx = mcp.get_context()
    # history = ctx.request_context.lifespan_context.history
    # messages = choose_option_prompt(scores, planned_controls, history)
    # langchain_messages = tuples_to_langchain_messages(messages)
    # response = llm.invoke(langchain_messages)
    # result = json.loads(response)

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
