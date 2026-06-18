"""LLM factory and message normalization utilities."""

import os
import re
import unicodedata

from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM, get_current_context_task
from flowcept.configs import AGENT


def build_llm_model(
    model_name=None,
    model_kwargs=None,
    service_provider=None,
    agent_id=BaseAgentContextManager.agent_id,
    track_tools=True,
    return_response_object=False,
) -> FlowceptLLM:
    """Build and return an LLM instance using agent configuration.

    Returns
    -------
    FlowceptLLM
        An initialized LLM object configured using the ``AGENT`` settings.
    """
    _model_kwargs = (AGENT.get("model_kwargs") or {}).copy()
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

        os.environ["SAMBASTUDIO_URL"] = os.environ.get("SAMBASTUDIO_URL", AGENT.get("llm_server_url"))
        os.environ["SAMBASTUDIO_API_KEY"] = os.environ.get("SAMBASTUDIO_API_KEY", AGENT.get("api_key"))

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
        base_url = os.environ.get("OPENAI_BASE_URL", AGENT.get("llm_server_url") or None)
        org = os.environ.get("OPENAI_ORG_ID", AGENT.get("organization", None))

        init_kwargs = {"api_key": api_key}
        if base_url:
            init_kwargs["base_url"] = base_url
        if org:
            init_kwargs["organization"] = org

        llm = ChatOpenAI(**init_kwargs, **_model_kwargs)
    elif _service_provider == "google":
        if "claude" in _model_kwargs["model"]:
            api_key = os.environ.get("GOOGLE_API_KEY", AGENT.get("api_key", None))
            _model_kwargs["model_id"] = _model_kwargs.pop("model")
            _model_kwargs["google_token_auth"] = api_key
            from flowcept.agents.llm.providers.claude_gcp import ClaudeOnGCPLLM

            llm = ClaudeOnGCPLLM(**_model_kwargs)
        elif "gemini" in _model_kwargs["model"]:
            from flowcept.agents.llm.providers.gemini25 import Gemini25LLM

            llm = Gemini25LLM(**_model_kwargs)
    else:
        raise Exception("Currently supported providers are sambanova, openai, azure, and google.")

    if track_tools:
        llm = FlowceptLLM(llm, return_response_object=return_response_object)
        if agent_id is None:
            agent_id = BaseAgentContextManager.agent_id
        llm.agent_id = agent_id
        tool_task = get_current_context_task()
        if tool_task:
            llm.parent_task_id = tool_task.task_id
    return llm


def normalize_message(user_msg: str) -> str:
    """Normalize a user message into a canonical, comparison-friendly form.

    Parameters
    ----------
    user_msg : str
        Raw user input message.

    Returns
    -------
    str
        Normalized message suitable for matching, comparison, or hashing.
    """
    user_msg = user_msg.strip()
    user_msg = unicodedata.normalize("NFKC", user_msg)
    user_msg = user_msg.replace("–", "-").replace("—", "-")
    user_msg = re.sub(r"\s+", " ", user_msg)
    user_msg = re.sub(r"[?!.\s]+$", "", user_msg)
    return user_msg.lower()
