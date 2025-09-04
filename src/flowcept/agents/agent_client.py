import asyncio
from typing import Dict, List, Callable

from flowcept.configs import AGENT_HOST, AGENT_PORT
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent


def run_tool(
    tool_name: str | Callable, kwargs: Dict = None, host: str = AGENT_HOST, port: int = AGENT_PORT
) -> List[str]:
    """
    Run a tool using an MCP client session via a local streamable HTTP connection.

    This function opens an asynchronous connection to a local MCP server,
    initializes a session, and invokes a specified tool with optional arguments.
    The tool's response content is returned as a list of `TextContent` objects.

    Parameters
    ----------
    tool_name : str
        The name of the tool to call within the MCP framework.
    kwargs : Dict, optional
        A dictionary of keyword arguments to pass as input to the tool. Defaults to None.

    Returns
    -------
    List[TextContent]
        A list of `TextContent` objects returned by the tool execution.

    Notes
    -----
    This function uses `asyncio.run`, so it must not be called from an already-running
    event loop (e.g., inside another async function in environments like Jupyter).
    """
    if isinstance(tool_name, Callable):
        tool_name = tool_name.__name__

    async def _run():
        mcp_url = f"http://{host}:{port}/mcp"
        print(mcp_url)
        print(tool_name)

        async with streamablehttp_client(mcp_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result: List[TextContent] = await session.call_tool(tool_name, arguments=kwargs)
                actual_result = []
                for r in result.content:
                    if isinstance(r, str):
                        actual_result.append(r)
                    else:
                        actual_result.append(r.text)

                return actual_result

    return asyncio.run(_run())
