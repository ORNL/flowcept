"""MQ redis module."""

from typing import Callable
import redis

import msgpack
from time import time, sleep

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.utils import perf_log
from flowcept.configs import (
    MQ_CHANNEL,
    PERF_LOG,
)


class MQDaoRedis(MQDao):
    """MQ redis class."""

    MESSAGE_TYPES_IGNORE = {"psubscribe"}

    def __init__(self, adapter_settings=None):
        super().__init__(adapter_settings)
        self._producer = self._keyvalue_dao.redis_conn  # if MQ is redis, we use the same KV for the MQ
        self._consumer = None

    def subscribe(self):
        """
        Subscribe to interception channel.
        """
        self._consumer = self._keyvalue_dao.redis_conn.pubsub()
        self._consumer.psubscribe(MQ_CHANNEL)

    def message_listener(self, message_handler: Callable):
        """Get message listener with automatic reconnection."""
        max_retrials = 10
        current_trials = 0
        should_continue = True
        while should_continue and current_trials < max_retrials:
            try:
                for message in self._consumer.listen():
                    if message and message["type"] in MQDaoRedis.MESSAGE_TYPES_IGNORE:
                        continue
                    try:
                        msg_obj = msgpack.loads(message["data"], strict_map_key=False)
                        if not message_handler(msg_obj):
                            should_continue = False  # Break While loop
                            break  # Break For loop
                    except Exception as e:
                        self.logger.error(f"Failed to process message: {e}")

                    current_trials = 0
            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                current_trials += 1
                self.logger.critical(f"Redis connection lost: {e}. Reconnecting in 3 seconds...")
                sleep(3)
            except Exception as e:
                self.logger.exception(e)
                break

    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send the message."""
        self._producer.publish(channel, serializer(message))

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        pipe = self._producer.pipeline()
        for message in buffer:
            try:
                pipe.publish(MQ_CHANNEL, serializer(message))
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        t0 = 0
        if PERF_LOG:
            t0 = time()
        try:
            pipe.execute()
            # self.logger.debug(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)
        perf_log("mq_pipe_execute", t0)

    def liveness_test(self):
        """Get the livelyness of it."""
        try:
            return super().liveness_test()
        except Exception as e:
            self.logger.exception(e)
            return False
