from abc import abstractmethod
from threading import Thread
from typing import Callable, Dict, Tuple, Optional

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import MQ_ENABLED


class BaseConsumer(object):
    """
    Abstract base class for message consumers in a pub-sub architecture.

    This class provides a standard interface and shared logic for subscribing to
    message queues and dispatching messages to a handler.

    Note
    ----
    The MQ-disabled path is only intended for agent consumers that can operate
    from an offline buffer file. General consumers that require MQ should keep
    the default behavior (raise when MQ_ENABLED is False).
    """

    def __init__(self, allow_mq_disabled: bool = False):
        """Initialize the message queue DAO and logger."""
        self.logger = FlowceptLogger()
        self._main_thread: Optional[Thread] = None

        if not MQ_ENABLED:
            if allow_mq_disabled:
                self._mq_dao = None
                self.logger.warning("MQ is disabled; starting consumer without a message queue.")
                return
            raise Exception("MQ is disabled in the settings. You cannot consume messages.")

        self._mq_dao = MQDao.build()

    @abstractmethod
    def message_handler(self, msg_obj: Dict) -> bool:
        """
        Handle a single incoming message.

        Parameters
        ----------
        msg_obj : dict
            The parsed message object received from the queue.

        Returns
        -------
        bool
            Return False to break the message listener loop.
            Return True to continue listening.
        """
        pass

    def start(self, target: Callable = None, args: Tuple = (), threaded: bool = True, daemon=False):
        """
        Start the consumer by subscribing and launching the message handler.

        Parameters
        ----------
        target : Callable
            The function to run for listening to messages (usually the message loop).
        args : tuple, optional
            Arguments to pass to the target function.
        threaded : bool, default=True
            Whether to run the target function in a background thread.
        daemon: bool

        Returns
        -------
        BaseConsumer
            The current instance (to allow chaining).
        """
        if self._mq_dao is None:
            self.logger.warning("MQ is disabled; skipping message consumption start.")
            return self
        if target is None:
            target = self.default_thread_target
        self._mq_dao.subscribe()
        if threaded:
            self._main_thread = Thread(target=target, args=args, daemon=daemon)
            self._main_thread.start()
        else:
            target(*args)
        return self

    def default_thread_target(self):
        """
        The default message consumption loop.

        This method is used as the default thread target when starting the consumer. It listens for
        messages from the message queue and passes them to the consumer's `message_handler`.

        Typically run in a background thread when `start()` is called without a custom target.

        See Also
        --------
        start : Starts the consumer and optionally spawns a background thread to run this method.
        """
        if self._mq_dao is None:
            self.logger.warning("MQ is disabled; no message listener will run.")
            return
        self.logger.debug("Going to wait for new messages!")
        self._mq_dao.message_listener(self.message_handler)
        self.logger.debug("Broke main message listening loop!")
        # self._mq_dao.stop(check_safe_stops=False) # TODO Do we need to stop mq_dao here?
        self.stop_consumption()
        self.logger.debug("MQ stopped.")

    def stop_consumption(self):
        """
        Stop consuming messages by unsubscribing from the message queue.
        """
        if self._mq_dao is None:
            return
        self._mq_dao.unsubscribe()
