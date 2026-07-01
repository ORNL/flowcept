import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, List
from uuid import uuid4

from flowcept.configs import AGENT
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.consumers.base_consumer import BaseConsumer


@dataclass
class BaseAppContext:
    """
    Container for storing agent context data during the lifespan of an application session.

    Attributes
    ----------
    tasks : list of dict
        A list of task messages received from the message queue. Each task message is stored as a dictionary.
    """

    tasks: List[Dict]

    def reset_context(self):
        """
        Method to reset the variables in the context.
        """
        self.tasks = []
        self.workflow_msg_obj = {}
        self.objects = []


class BaseAgentContextManager(BaseConsumer):
    """
    Base class for any MCP Agent that wants to participate in the Flowcept ecosystem.

    With ``stateless_http=True`` (FastMCP), the lifespan runs once per HTTP request.
    A class-level lock prevents concurrent requests from racing to stop the shared
    Flowcept instance when multiple tool calls execute simultaneously.

    Agents inheriting from this class can:
    - Subscribe to and consume messages from the Flowcept-compatible message queue (MQ)
    - Handle task-related messages and accumulate them in context
    - Gracefully manage their lifecycle using an async context manager
    - Interact with Flowcept’s provenance system to read/write messages, query databases, and store chat history

    To integrate with Flowcept:
    - Inherit from `BaseAgentContextManager`
    - Override `message_handler()` if custom message handling is needed
    - Access shared state via `self.context` during execution
    """

    agent_id = None
    _stop_lock = threading.Lock()

    def __init__(self, allow_mq_disabled: bool = False):
        """
        Initializes the agent and resets its context state.
        """
        super().__init__(allow_mq_disabled=allow_mq_disabled)
        if not hasattr(self, "context"):
            self.context: BaseAppContext = None
        self.agent_id = BaseAgentContextManager.agent_id

    def message_handler(self, msg_obj: Dict) -> bool:
        """
        Handles a single message received from the message queue.

        Parameters
        ----------
        msg_obj : dict
            The message received, typically structured with a "type" field.

        Returns
        -------
        bool
            Return True to continue listening for messages, or False to stop the loop.

        Notes
        -----
        This default implementation stores messages of type 'task' in the internal context.
        Override this method in a subclass to handle other message types or implement custom logic.
        """
        msg_type = msg_obj.get("type", None)
        msg_subtype = msg_obj.get("subtype", "")
        if msg_type == "task":
            self.logger.debug("Received task msg!")
            if msg_subtype not in {"llm_query"}:
                self.context.tasks.append(msg_obj)
        elif msg_type == "object":
            self.context.objects.append(msg_obj)

        return True

    def start_consumer(self):
        """Start the Flowcept instance and MQ consumer.

        Called by ``FlowceptMCPServer.start()`` so the consumer is live before any HTTP request
        arrives. Idempotent: a second call is a no-op.
        """
        if getattr(self, "_consumer_started", False):
            return
        self._consumer_started = True
        self.agent_id = BaseAgentContextManager.agent_id = str(uuid4())
        self.logger.info(f"Starting consumer for agent {self.agent_id}.")
        start_persistence = AGENT.get("start_persistence", False)
        self.flowcept_instance = Flowcept(
            start_persistence=start_persistence,
            save_workflow=False,
            check_safe_stops=False,
            workflow_name="flowcept_agent_workflow",
            agent_id=self.agent_id,
        )
        self.agent_workflow_id = self.flowcept_instance.current_workflow_id
        self.flowcept_instance.start()
        self.flowcept_instance.logger.info(
            f"This section’s workflow_id={Flowcept.current_workflow_id}, campaign_id={Flowcept.campaign_id}"
        )
        # Daemon thread: the agent has no flush-on-stop obligations (persistence is off), and a
        # blocked MQ listen must never prevent the hosting process from exiting.
        self.start(daemon=True)

    def stop_consumer(self):
        """Stop the MQ consumer and Flowcept instance.

        Called by ``FlowceptMCPServer.stop()``. Idempotent: safe to call multiple times.
        """
        if not getattr(self, "_consumer_started", False):
            return
        self._consumer_started = False
        try:
            self.stop_consumption()
        except Exception as e:
            self.logger.warning(f"stop_consumption raised during teardown: {e}")
        with BaseAgentContextManager._stop_lock:
            if getattr(self, "flowcept_instance", None) is not None:
                try:
                    self.flowcept_instance.stop()
                except Exception as e:
                    self.logger.warning(f"flowcept_instance.stop() raised during teardown: {e}")
                self.flowcept_instance = None

    @asynccontextmanager
    async def lifespan(self, app):
        """
        Async context manager for the agent’s ASGI lifecycle.

        The consumer is started externally via ``start_consumer()`` (called by
        ``FlowceptMCPServer.start()``); this lifespan only exposes the context to the
        framework and delegates to subclasses for any additional setup.

        Parameters
        ----------
        app : Any
            The application instance (included for ASGI compatibility).

        Yields
        ------
        BaseAppContext
            The current application context.
        """
        yield self.context
