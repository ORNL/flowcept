import os
from typing import List, Union, Tuple

from langchain.chains.conversation.base import ConversationChain
from langchain_community.llms.sambanova import SambaStudio
from mcp.server.fastmcp.prompts import base
from langchain_core.language_models import LLM
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from flowcept.configs import AGENT

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")


def count_tokens(prompt: str) -> int:
    """
    Rough estimate of token count based on average English word-to-token ratio.
    Assumes 1 token ≈ 4 characters (common for LLaMA, GPT-like models).
    """
    return int(len(prompt) / 4)


def build_llm_model(model_name=None, model_kwargs=None) -> LLM:
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
    llm = SambaStudio(model_kwargs=_model_kwargs)

    return llm


def get_llm_chain(memory) -> LLM:
    """
    Build and return an LLM instance using agent configuration.

    This function retrieves the model name and keyword arguments from the AGENT configuration,
    constructs a SambaStudio LLM instance, and returns it.

    Returns
    -------
    LLM
        An initialized LLM object configured using the `AGENT` settings.
    """
    llm = build_llm_model()
    chain = ConversationChain(
        llm=llm,
        memory=memory,
        verbose=True  # optional for debugging
    )
    return chain


def convert_mcp_messages_to_plain_text(messages: list[base.Message]) -> str:
    """
    Convert a list of MCP base.Message objects into a plain text dialogue.

    Parameters
    ----------
    messages : list of BaseMessage
        The list of messages, typically from HumanMessage, AIMessage, SystemMessage, etc.

    Returns
    -------
    str
        A plain text version of the conversation, with roles labeled.
    """
    lines = []
    for message in messages:
        role = message.role.capitalize()  # e.g., "human" → "Human"
        line = f"{role}: {message.content.text}"
        lines.append(line)
    return "\n".join(lines)


def convert_mcp_to_langchain(messages: list[base.Message]) -> List[Union[HumanMessage, AIMessage]]:
    """
    Convert a list of MCP-style messages to LangChain-compatible message objects.

    Parameters
    ----------
    messages : list of base.Message
        A list of messages in the MCP message format, each with a `role` and `content`.

    Returns
    -------
    list of Union[HumanMessage, AIMessage]
        A list of LangChain message objects, converted from the original MCP format.

    Raises
    ------
    ValueError
        If a message has a role that is not 'user' or 'assistant'.

    Notes
    -----
    This function extracts the `text` attribute from message content if present, falling back to `str(content)`
    otherwise. It maps MCP 'user' roles to LangChain `HumanMessage` and 'assistant' roles to `AIMessage`.
    """
    converted = []
    for m in messages:
        if not hasattr(m, "content"):
            raise ValueError(f"Message {m} does not have the expected format.")
        if hasattr(m.content, "text"):
            content = m.content.text
        else:
            content = str(m.content)  # fallback if it's already a string

        if m.role == "user":
            converted.append(HumanMessage(content=content))
        elif m.role == "assistant":
            converted.append(AIMessage(content=content))
        else:
            raise ValueError(f"Unsupported role: {m.role}")
    return converted

def tuples_to_langchain_messages(tuples: List[Tuple[str, str]]) -> List:
    """
    Convert a list of (role, message) tuples to LangChain messages.

    Parameters
    ----------
    tuples : List[Tuple[str, str]]
        List of tuples where the first element is the role ('human' or 'system'),
        and the second element is the message string.

    Returns
    -------
    List[HumanMessage | SystemMessage]
        List of LangChain message objects corresponding to the input tuples.
    """
    messages = []
    for role, text in tuples:
        role_lower = role.lower()
        if role_lower == "human" or role_lower == "user": # TODO change to use Constants
            messages.append(HumanMessage(content=text))
        elif role_lower == "system":
            messages.append(SystemMessage(content=text))
        elif role_lower == "assistant":
            messages.append(AIMessage(content=text))
        else:
            raise ValueError(f"Unknown role: {role}. Expected 'human' or 'system'.")
    return messages


def flatten_prompt_messages(messages: list[tuple[str, str]]) -> str:
    role_map = {
        "system": "System",
        "user": "User",
        "assistant": "Assistant"
    }
    return "\n\n".join(f"{role_map.get(role, role)}:\n{content}" for role, content in messages)

