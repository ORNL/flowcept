import json
import os
from threading import Thread

from flowcept.agents import check_liveness
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
        self.buffer_path = buffer_path
        self.logger = FlowceptLogger()
        self._server_thread: Thread | None = None
        self._server = None

    def _load_buffer_once(self) -> int:
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
        config = uvicorn.Config(mcp_flowcept.streamable_http_app, host=AGENT_HOST, port=AGENT_PORT, lifespan="on")
        self._server = uvicorn.Server(config)
        self._server.run()

    def start(self):
        if not MQ_ENABLED:
            self._load_buffer_once()

        self._server_thread = Thread(target=self._run_server, daemon=False)
        self._server_thread.start()
        self.logger.info(f"Flowcept agent server started on {AGENT_HOST}:{AGENT_PORT}")
        return self

    def stop(self):
        if self._server is not None:
            self._server.should_exit = True
        if self._server_thread is not None:
            self._server_thread.join(timeout=5)

    def wait(self):
        if self._server_thread is not None:
            self._server_thread.join()

    def query(self, message: str):
        """
        Send a prompt to the agent's main router tool and return the response.
        """
        return run_tool(tool_name=prompt_handler, kwargs={"message": message})[0]


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
