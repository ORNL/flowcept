import os
from typing import Union, Dict

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM, get_current_context_task
from langchain_core.language_models import LLM

from flowcept.configs import AGENT
from pydantic import BaseModel



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


def build_llm_model(model_name=None, model_kwargs=None, service_provider=None, agent_id=BaseAgentContextManager.agent_id, track_tools=True) -> FlowceptLLM:
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

    if "model" not in _model_kwargs:
        _model_kwargs["model"] = AGENT.get("model", model_name)

    if service_provider:
        _service_provider = service_provider
    else:
        _service_provider = AGENT.get("service_provider")

    if _service_provider == "sambanova":
        from langchain_community.llms.sambanova import SambaStudio
        os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
        os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")

        llm = SambaStudio(model_kwargs=_model_kwargs)
    elif _service_provider == "azure":
        from langchain_openai.chat_models.azure import AzureChatOpenAI
        api_key = os.environ.get("AZURE_OPENAI_API_KEY", AGENT.get("api_key", None))
        service_url = os.environ.get("AZURE_OPENAI_API_ENDPOINT", AGENT.get("llm_server_url", None))
        llm = AzureChatOpenAI(
            azure_deployment=_model_kwargs.get("model"),
            azure_endpoint=service_url,
            api_key=api_key,
            **_model_kwargs
        )
    elif _service_provider == "openai":
        from langchain_openai import ChatOpenAI
        api_key = os.environ.get("OPENAI_API_KEY", AGENT.get("api_key", None))
        llm = ChatOpenAI(openai_api_key=api_key, **model_kwargs)
    else:
        raise Exception("Currently supported providers are sambanova, openai, and azure.")
    if track_tools:
        llm = FlowceptLLM(llm)
        if agent_id is None:
            agent_id = BaseAgentContextManager.agent_id
        llm.agent_id = agent_id
        if track_tools:
            tool_task = get_current_context_task()
            if tool_task:
                llm.parent_task_id = tool_task.task_id
    return llm
