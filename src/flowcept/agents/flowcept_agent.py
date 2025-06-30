from flowcept.agents.flowcept_ctx_manager import mcp_flowcept
from flowcept.configs import AGENT_HOST, AGENT_PORT
from flowcept.flowcept_api.flowcept_controller import Flowcept

import uvicorn


def main():
    """
    Start the MCP server.
    """
    f = Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False).start()
    f.logger.info(f"This section's workflow_id={Flowcept.current_workflow_id}")
    uvicorn.run(
        mcp_flowcept.streamable_http_app, host=AGENT_HOST, port=AGENT_PORT, lifespan="on"
    )


if __name__ == "__main__":
    main()
