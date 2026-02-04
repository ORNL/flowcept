import json
import os
from threading import Thread

from flowcept.agents import check_liveness
from flowcept.agents.agents_utils import ToolResult
from flowcept.agents.tools.general_tools import prompt_handler
from flowcept.agents.agent_client import run_tool
from flowcept.agents.flowcept_ctx_manager import mcp_flowcept, ctx_manager
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_HOST, AGENT_PORT, DUMP_BUFFER_PATH, MQ_ENABLED
from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from uuid import uuid4

import uvicorn


class FlowceptAgent:
    """
    Flowcept agent server wrapper with optional offline buffer loading.
    """

    def __init__(self, buffer_path: str | None = None):
        """
        Initialize a FlowceptAgent.

        Parameters
        ----------
        buffer_path : str or None
            Optional path to a JSONL buffer file. When MQ is disabled, the agent
            loads this file once at startup.
        """
        self.buffer_path = buffer_path
        self.logger = FlowceptLogger()
        self._server_thread: Thread | None = None
        self._server = None

    def _load_buffer_once(self) -> int:
        """
        Load messages from a JSONL buffer file into the agent context.

        Returns
        -------
        int
            Number of messages loaded.
        """
        path = self.buffer_path or DUMP_BUFFER_PATH
        if not os.path.exists(path):
            raise FileNotFoundError(f"Buffer file not found: {path}")

        count = 0
        self.logger.info(f"Loading agent buffer from {path}")
        if ctx_manager.agent_id is None:
            agent_id = str(uuid4())
            BaseAgentContextManager.agent_id = agent_id
            ctx_manager.agent_id = agent_id
        with open(path, "r") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                msg_obj = json.loads(line)
                ctx_manager.message_handler(msg_obj)
                count += 1
        self.logger.info(f"Loaded {count} messages from buffer.")
        return count

    def _run_server(self):
        """Run the MCP server (blocking call)."""
        config = uvicorn.Config(mcp_flowcept.streamable_http_app, host=AGENT_HOST, port=AGENT_PORT, lifespan="on")
        self._server = uvicorn.Server(config)
        self._server.run()

    def start(self):
        """
        Start the agent server in a background thread.

        Returns
        -------
        FlowceptAgent
            The current instance.
        """
        if not MQ_ENABLED:
            self._load_buffer_once()

        self._server_thread = Thread(target=self._run_server, daemon=False)
        self._server_thread.start()
        self.logger.info(f"Flowcept agent server started on {AGENT_HOST}:{AGENT_PORT}")
        return self

    def stop(self):
        """Stop the agent server and wait briefly for shutdown."""
        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)

    def wait(self):
        """Block until the server thread exits."""
        if self._server_thread is not None:
            self._server_thread.join()

    def query(self, message: str) -> ToolResult:
        """
        Send a prompt to the agent's main router tool and return the response.
        """
        try:
            resp = run_tool(tool_name=prompt_handler, kwargs={"message": message})[0]
        except Exception as e:
            return ToolResult(code=400, result=f"Error executing tool prompt_handler: {e}", tool_name="prompt_handler")

        try:
            return ToolResult(**json.loads(resp))
        except Exception as e:
            return ToolResult(
                code=499,
                result=f"Could not parse tool response as JSON: {resp}",
                extra=str(e),
                tool_name="prompt_handler",
            )


def main():
    """
    Start the MCP server.
    """
    agent = FlowceptAgent().start()
    # Wake up tool call
    print(run_tool(check_liveness, host=AGENT_HOST, port=AGENT_PORT)[0])
    agent.wait()


if __name__ == "__main__":
    main()
