from typing import Dict, List

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client
from mcp.types import TextContent


def run_tool(tool_name: str, kwargs: Dict = None) -> List[TextContent]:
    import asyncio

    async def _run():

        async with streamablehttp_client("http://127.0.0.1:8000/mcp") as (read, write, _):  # TODO dynamic config
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments=kwargs)
                return result.content

    return asyncio.run(_run())
