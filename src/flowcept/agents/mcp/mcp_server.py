"""MCP server entry point for the Flowcept agent."""

import json
import os
import socket
import time
from threading import Thread

from flowcept.agents.mcp.mcp_client import run_tool
from flowcept.agents.mcp.context_manager import mcp_flowcept, ctx_manager

# Import all mcp_tools modules so their @mcp_flowcept.tool() decorators fire
from flowcept.agents.mcp.mcp_tools.session_tools import check_liveness
import flowcept.agents.mcp.mcp_tools.db_query_mcp_tools  # noqa: F401
import flowcept.agents.mcp.mcp_tools.dashboard_mcp_tools  # noqa: F401
import flowcept.agents.mcp.mcp_tools.df_query_mcp_tools  # noqa: F401
import flowcept.agents.mcp.mcp_tools.report_tools  # noqa: F401
import flowcept.agents.mcp.mcp_tools.schema_mcp_tools  # noqa: F401
import flowcept.agents.mcp.mcp_prompts  # noqa: F401
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_HOST, AGENT_PORT, DUMP_BUFFER_PATH
from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager
from uuid import uuid4

import uvicorn


class FlowceptMCPServer:
    """Flowcept mcp server wrapper with optional offline buffer loading."""

    def __init__(self, buffer_path: str | None = None, buffer_messages: list[dict] | None = None):
        """Initialize a Flowcept MCP server.

        Parameters
        ----------
        buffer_path : str or None
            Optional path to a JSONL buffer file.
        buffer_messages : list[dict] or None
            Optional list of buffer messages to load directly into the agent context.
        """
        self.buffer_path = buffer_path
        self.buffer_messages = buffer_messages
        self.logger = FlowceptLogger()
        self._server_thread: Thread | None = None
        self._server = None

    def _load_buffer_messages(self, messages: list[dict]) -> int:
        """Load a list of message objects into the agent context.

        Returns
        -------
        int
            Number of messages loaded.
        """
        count = 0
        if ctx_manager.agent_id is None:
            agent_id = str(uuid4())
            BaseAgentContextManager.agent_id = agent_id
            ctx_manager.agent_id = agent_id
        for msg_obj in messages:
            ctx_manager.message_handler(msg_obj)
            count += 1
        self.logger.info(f"Loaded {count} messages from buffer list.")
        return count

    def reset_context(self):
        """Reset the MCP agent context without restarting the HTTP server."""
        ctx_manager.reset_context()

    def load_buffer_messages(self, messages: list[dict]) -> int:
        """Replace the active MCP context with the provided buffer messages."""
        self.reset_context()
        return self._load_buffer_messages(messages)

    def _load_buffer_once(self) -> int:
        """Load messages from a JSONL buffer file into the agent context.

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
        try:
            from sse_starlette.sse import AppStatus

            AppStatus.should_exit_event = None
        except ImportError:
            pass
        config = uvicorn.Config(mcp_flowcept.streamable_http_app, host=AGENT_HOST, port=AGENT_PORT, lifespan="on")
        self._server = uvicorn.Server(config)
        self._server.run()

    def start(self):
        """Start the agent server in a background thread.

        Returns
        -------
        FlowceptMCPServer
            The current instance.
        """
        if self.buffer_path is not None or self.buffer_messages is not None:
            self.reset_context()
        if self.buffer_messages is not None:
            self._load_buffer_messages(self.buffer_messages)
        elif self.buffer_path is not None:
            self._load_buffer_once()
        else:
            ctx_manager.start_consumer()

        self._server_thread = Thread(target=self._run_server, daemon=True)
        self._server_thread.start()
        self._wait_until_ready()
        self.logger.info(f"Flowcept mcp server started on {AGENT_HOST}:{AGENT_PORT}")
        return self

    def _wait_until_ready(self, timeout_sec: float = 10.0):
        """Wait until the local MCP TCP listener accepts connections."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                with socket.create_connection((AGENT_HOST, AGENT_PORT), timeout=0.2):
                    return
            except OSError:
                time.sleep(0.05)
        raise TimeoutError(f"Flowcept MCP server did not start on {AGENT_HOST}:{AGENT_PORT}.")

    def _wait_until_stopped(self, timeout_sec: float = 10.0):
        """Wait until the local MCP TCP listener stops accepting connections."""
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                with socket.create_connection((AGENT_HOST, AGENT_PORT), timeout=0.2):
                    time.sleep(0.05)
            except OSError:
                return
        self.logger.warning(f"Flowcept MCP server still appears reachable on {AGENT_HOST}:{AGENT_PORT}.")

    def stop(self):
        """Stop the agent server and wait briefly for shutdown."""
        if self._server is None and self._server_thread is not None:
            self._server_thread.join(timeout=1)
        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)
            if self._server_thread.is_alive():
                self.logger.warning("Agent server thread did not stop within 5s; continuing shutdown.")
        self._wait_until_stopped()
        ctx_manager.stop_consumer()

    def wait(self):
        """Block until the server thread exits."""
        if self._server_thread is not None:
            self._server_thread.join()


def main():
    """Start the MCP server."""
    agent = FlowceptMCPServer().start()
    print(run_tool(check_liveness, host=AGENT_HOST, port=AGENT_PORT)[0])
    agent.wait()


if __name__ == "__main__":
    main()
