import os
from typing import Union, Dict

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM, get_current_context_task_id
from langchain_community.llms.sambanova import SambaStudio
from langchain_core.language_models import LLM

from flowcept.configs import AGENT
from pydantic import BaseModel

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")


class ToolResult(BaseModel):
    """

    Conventions:

    - code 2xx: Success
        → result is the expected output, a string
           201, all good
    - code 3xx: Success
        → result is the expected output, a dict
           301: all good
    - code 4xx: System or agent internal errors → result is a string with an error message
           400: problem with llm call, like server connection or token issues
           404: Empty or none result
           405: llm responded but format was probably wrong
           406: error executing python code
           499: some other error
    - code 5xx: System or agent internal errors → result is a dict with structured error info
    - code None: result not yet set or tool didn't return anything

    """
    code: int | None = None
    result: Union[str, Dict] = None
    extra: Dict | str | None = None
    tool_name: str | None = None

    def result_is_str(self) -> bool:
        return (200 <= self.code < 300) or (400 <= self.code < 500)

    def is_success(self):
        return self.is_success_string() or self.is_success_dict()

    def is_success_string(self):
        return 200 <= self.code < 300

    def is_error_string(self):
        return 400 <= self.code < 500

    def is_success_dict(self) -> bool:
        return 300 <= self.code < 400


def build_llm_model(model_name=None, model_kwargs=None, agent_id=BaseAgentContextManager.agent_id) -> FlowceptLLM:
    """
    Build and return an LLM instance using agent configuration.

    This function retrieves the model name and keyword arguments from the AGENT configuration,
    constructs a SambaStudio LLM instance, and returns it.

    Returns
    -------
    LLM
        An initialized LLM object configured using the `AGENT` settings.
    """
    _model_kwargs = AGENT.get("model_kwargs", {}).copy()
    if model_kwargs is not None:
        for k in model_kwargs:
            _model_kwargs[k] = model_kwargs[k]
    _model_kwargs["model"] = AGENT.get("model", model_name)

    llm = FlowceptLLM(SambaStudio(model_kwargs=_model_kwargs))
    if agent_id is None:
        agent_id = BaseAgentContextManager.agent_id
    llm.agent_id = agent_id
    tool_task_id = get_current_context_task_id()
    llm.parent_task_id = tool_task_id
    return llm
