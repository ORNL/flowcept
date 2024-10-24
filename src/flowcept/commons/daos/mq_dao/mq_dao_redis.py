"""MQ redis module."""

from typing import Callable

import msgpack
from time import time

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

    def message_listener(self, message_handler: Callable):
        """Get message listener."""
        pubsub = self._kv_conn.pubsub()
        pubsub.psubscribe(MQ_CHANNEL)
        for message in pubsub.listen():
            self.logger.debug("Received a message!")
            if message["type"] in MQDaoRedis.MESSAGE_TYPES_IGNORE:
                continue
            msg_obj = msgpack.loads(
                message["data"]  # , cls=DocumentInserter.DECODER
            )
            if not message_handler(msg_obj):
                break

    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send the message."""
        self._producer.publish(channel, serializer(message))

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        pipe = self._producer.pipeline()
        for message in buffer:
            try:
                self.logger.debug(
                    f"Going to send Message:" f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
                )
                pipe.publish(MQ_CHANNEL, serializer(message))
            except Exception as e:
                self.logger.exception(e)
                self.logger.error(
                    "Some messages couldn't be flushed! Check the messages' contents!"
                )
                self.logger.error(f"Message that caused error: {message}")
        t0 = 0
        if PERF_LOG:
            t0 = time()
        try:
            pipe.execute()
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
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
