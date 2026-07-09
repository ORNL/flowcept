import asyncio
import json
import re
from typing import Dict, List, Callable

from flowcept.configs import AGENT_HOST, AGENT_PORT
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent


async def _with_mcp_session(host: str, port: int, operation):
    """Open an MCP streamable HTTP session and run an async operation."""
    mcp_url = f"http://{host}:{port}/mcp"
    async with streamablehttp_client(mcp_url) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await operation(session)


def run_tool(
    tool_name: str | Callable,
    kwargs: Dict = None,
    host: str = AGENT_HOST,
    port: int = AGENT_PORT,
) -> List[str]:
    """
    Run a tool using an MCP client session via streamable HTTP.

    Parameters
    ----------
    tool_name : str | Callable
        MCP tool name (or callable whose ``__name__`` matches tool name).
    kwargs : Dict, optional
        Tool arguments.
    host : str, optional
        MCP host.
    port : int, optional
        MCP port.

    Returns
    -------
    List[str]
        Tool outputs normalized as JSON strings.
    """
    if isinstance(tool_name, Callable):
        tool_name = tool_name.__name__

    def _normalize_result(content: List[TextContent]) -> List[str]:
        actual_result = []
        for r in content:
            text = r if isinstance(r, str) else r.text
            try:
                json.loads(text)
                actual_result.append(text)
            except Exception:
                match = re.search(r"Error code:\\s*(\\d+)", text)
                code = int(match.group(1)) if match else 200
                actual_result.append(json.dumps({"code": code, "result": text, "tool_name": tool_name}))
        return actual_result

    async def _run():
        async def _operation(session):
            result: List[TextContent] = await session.call_tool(tool_name, arguments=kwargs)
            return _normalize_result(result.content)

        return await _with_mcp_session(host, port, _operation)

    return asyncio.run(_run())


def run_prompt(
    prompt_name: str,
    args: Dict | None = None,
    host: str = AGENT_HOST,
    port: int = AGENT_PORT,
) -> Dict:
    """
    Retrieve an MCP prompt payload from Flowcept Agent via streamable HTTP.

    Parameters
    ----------
    prompt_name : str
        MCP prompt name to retrieve.
    args : Dict, optional
        Prompt arguments.
    host : str, optional
        MCP host.
    port : int, optional
        MCP port.

    Returns
    -------
    Dict
        Dictionary with prompt metadata and rendered messages.
    """

    async def _run():
        async def _operation(session):
            result = await session.get_prompt(name=prompt_name, arguments=args)
            messages = []
            for msg in result.messages:
                content = getattr(msg, "content", None)
                text = getattr(content, "text", str(content))
                messages.append({"role": msg.role, "text": text})
            return {
                "description": result.description,
                "messages": messages,
            }

        return await _with_mcp_session(host, port, _operation)

    return asyncio.run(_run())
