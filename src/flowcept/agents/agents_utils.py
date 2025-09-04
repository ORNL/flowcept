import os
from typing import Union, Dict

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM, get_current_context_task

from flowcept.configs import AGENT
from pydantic import BaseModel


class ToolResult(BaseModel):
    """
    ToolResult is a standardized wrapper for tool outputs, encapsulating
    status codes, results, and optional metadata.

    This class provides conventions for interpreting the output of tools
    (e.g., LLM calls, DataFrame operations, plotting functions) and ensures
    consistent handling of both successes and errors.

    Conventions
    -----------
    - **2xx: Success (string result)**
      - Result is the expected output as a string.
      - Example: ``201`` → operation completed successfully.

    - **3xx: Success (dict result)**
      - Result is the expected output as a dictionary.
      - Example: ``301`` → operation completed successfully.

    - **4xx: Error (string message)**
      - System or agent internal error, returned as a string message.
      - ``400``: LLM call problem (e.g., server connection or token issues).
      - ``404``: Empty or ``None`` result.
      - ``405``: LLM responded, but format was wrong.
      - ``406``: Error executing Python code.
      - ``499``: Other uncategorized error.

    - **5xx: Error (dict result)**
      - System or agent internal error, returned as a structured dictionary.

    - **None**
      - Result not yet set or tool did not return anything.

    Attributes
    ----------
    code : int or None
        Status code indicating success or error category.
    result : str or dict, optional
        The main output of the tool (string, dict, or error message).
    extra : dict or str or None
        Additional metadata or debugging information.
    tool_name : str or None
        Name of the tool that produced this result.

    Methods
    -------
    result_is_str() -> bool
        Return True if the result should be interpreted as a string.
    is_success() -> bool
        Return True if the result represents any type of success.
    is_success_string() -> bool
        Return True if the result is a success with a string output (2xx).
    is_error_string() -> bool
        Return True if the result is an error with a string message (4xx).
    is_success_dict() -> bool
        Return True if the result is a success with a dict output (3xx).

    Examples
    --------
    >>> ToolResult(code=201, result="Operation successful")
    ToolResult(code=201, result='Operation successful')

    >>> ToolResult(code=301, result={"data": [1, 2, 3]})
    ToolResult(code=301, result={'data': [1, 2, 3]})

    >>> ToolResult(code=405, result="Invalid format from LLM")
    ToolResult(code=405, result='Invalid format from LLM')
    """

    code: int | None = None
    result: Union[str, Dict] = None
    extra: Dict | str | None = None
    tool_name: str | None = None

    def result_is_str(self) -> bool:
        """Returns True if the result is a string."""
        return (200 <= self.code < 300) or (400 <= self.code < 500)

    def is_success(self):
        """Returns True if the result is a success."""
        return self.is_success_string() or self.is_success_dict()

    def is_success_string(self):
        """Returns True if the result is a success string."""
        return 200 <= self.code < 300

    def is_error_string(self):
        """Returns True if the result is an error string."""
        return 400 <= self.code < 500

    def is_success_dict(self) -> bool:
        """Returns True if the result is a success dictionary."""
        return 300 <= self.code < 400


def build_llm_model(
    model_name=None,
    model_kwargs=None,
    service_provider=None,
    agent_id=BaseAgentContextManager.agent_id,
    track_tools=True,
) -> FlowceptLLM:
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
            azure_deployment=_model_kwargs.get("model"), azure_endpoint=service_url, api_key=api_key, **_model_kwargs
        )
    elif _service_provider == "openai":
        from langchain_openai import ChatOpenAI

        api_key = os.environ.get("OPENAI_API_KEY", AGENT.get("api_key", None))
        llm = ChatOpenAI(openai_api_key=api_key, **model_kwargs)
    elif _service_provider == "google":
        if "claude" in _model_kwargs["model"]:
            api_key = os.environ.get("GOOGLE_API_KEY", AGENT.get("api_key", None))
            _model_kwargs["model_id"] = _model_kwargs.pop("model")
            _model_kwargs["google_token_auth"] = api_key
            from flowcept.agents.llms.claude_gcp import ClaudeOnGCPLLM

            llm = ClaudeOnGCPLLM(**_model_kwargs)
        elif "gemini" in _model_kwargs["model"]:
            from flowcept.agents.llms.gemini25 import Gemini25LLM

            llm = Gemini25LLM(**_model_kwargs)

    else:
        raise Exception("Currently supported providers are sambanova, openai, azure, and google.")
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
