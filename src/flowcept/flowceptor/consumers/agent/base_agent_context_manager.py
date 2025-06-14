from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Dict, List

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


class BaseAgentContextManager(BaseConsumer):
    """
    Base class for any MCP Agent that wants to participate in the Flowcept ecosystem.

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

    def __init__(self):
        """
        Initializes the agent and resets its context state.
        """
        super().__init__()
        self.context = None
        self.reset_context()

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

        return True

    def reset_context(self):
        """
        Resets the internal context, clearing all stored task data.
        """
        self.context = BaseAppContext(tasks=[])

    @asynccontextmanager
    async def lifespan(self, app):
        """
        Async context manager to handle the agent’s lifecycle within an application.

        Starts the message consumption when the context is entered and stops it when exited.

        Parameters
        ----------
        app : Any
            The application instance using this context (typically unused but included for compatibility).

        Yields
        ------
        BaseAppContext
            The current application context, including collected tasks.
        """
        self.start()
        try:
            yield self.context
        finally:
            self.stop_consumption()
