from typing import List, Union

from langchain_community.llms.sambanova import SambaStudio
from mcp.server.fastmcp.prompts import base
from langchain_core.language_models import LLM
from langchain_core.messages import HumanMessage, AIMessage

from flowcept.configs import AGENT


def build_llm_model() -> LLM:
    """
    Build and return an LLM instance using agent configuration.

    This function retrieves the model name and keyword arguments from the AGENT configuration,
    constructs a SambaStudio LLM instance, and returns it.

    Returns
    -------
    LLM
        An initialized LLM object configured using the `AGENT` settings.
    """
    model_kwargs = AGENT.get("model_kwargs").copy()
    model_kwargs["model"] = AGENT.get("model")
    llm = SambaStudio(model_kwargs=model_kwargs)

    return llm


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
