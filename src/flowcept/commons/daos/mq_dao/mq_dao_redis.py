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

    def __init__(self, kv_host=None, kv_port=None, adapter_settings=None):
        super().__init__(kv_host, kv_port, adapter_settings)
        self._producer = self._kv_conn  # if MQ is redis, we use the same KV for the MQ
        self._consumer = None

    def subscribe(self):
        """
        Subscribe to interception channel.
        """
        self._consumer = self._kv_conn.pubsub()
        self._consumer.psubscribe(MQ_CHANNEL)
    
    def message_listener(self, message_handler: Callable):
        """Get message listener with automatic reconnection."""
        while True:
            try:
                self.logger.debug("Connecting to Redis...")
                for message in self._consumer.listen():
                    if message and message["type"] in MQDaoRedis.MESSAGE_TYPES_IGNORE:
                        continue
                    
                    self.logger.debug("Received a message!")

                    try:
                        msg_obj = msgpack.loads(
                            message["data"], strict_map_key=False
                        )
                        if not message_handler(msg_obj):
                            break
                    except Exception as e:
                        self.logger.error(f"Failed to process message: {e}")

            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                self.logger.critical(f"Redis connection lost: {e}. Reconnecting in 3 seconds...")
                sleep(3)
                
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
            super().liveness_test()
            return True
        except Exception as e:
            self.logger.exception(e)
            return False
