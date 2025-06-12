"""MQ redis module."""

from typing import Callable
import redis

import msgpack
from time import time, sleep

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.daos.redis_conn import RedisConn
from flowcept.configs import MQ_CHANNEL, MQ_HOST, MQ_PORT, MQ_PASSWORD, MQ_URI, MQ_SETTINGS, KVDB_ENABLED


class MQDaoRedis(MQDao):
    """MQ redis class."""

    MESSAGE_TYPES_IGNORE = {"psubscribe"}

    def __init__(self, adapter_settings=None):
        super().__init__(adapter_settings)

        self._consumer = None
        use_same_as_kv = MQ_SETTINGS.get("same_as_kvdb", False)
        if use_same_as_kv:
            if KVDB_ENABLED:
                self._producer = self._keyvalue_dao.redis_conn
            else:
                raise Exception("You have same_as_kvdb in your settings, but kvdb is disabled.")
        else:
            self._producer = RedisConn.build_redis_conn_pool(
                host=MQ_HOST, port=MQ_PORT, password=MQ_PASSWORD, uri=MQ_URI
            )

    def subscribe(self):
        """
        Subscribe to interception channel.
        """
        self._consumer = self._producer.pubsub()
        self._consumer.psubscribe(MQ_CHANNEL)

    def unsubscribe(self):
        """
        Unsubscribe to interception channel.
        """
        self._consumer.unsubscribe(MQ_CHANNEL)

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

                    if not isinstance(message["data"], (bytes, bytearray)):
                        self.logger.warning(
                            f"Skipping message with unexpected data type: {type(message['data'])} - {message['data']}"
                        )
                        continue

                    try:
                        msg_obj = msgpack.loads(message["data"], strict_map_key=False)
                        # self.logger.debug(f"In mq dao redis, received msg!  {msg_obj}")
                        if not message_handler(msg_obj):
                            should_continue = False  # Break While loop
                            break  # Break For loop
                    except Exception as e:
                        self.logger.error(f"Failed to process message {message}")
                        self.logger.exception(e)

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

    def _send_message_timed(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send the message using timing for performance evaluation."""
        t1 = time()
        self.send_message(message, channel, serializer)
        t2 = time()
        self._flush_events.append(["single", t1, t2, t2 - t1, len(str(message).encode())])

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        pipe = self._producer.pipeline()
        for message in buffer:
            try:
                pipe.publish(channel, serializer(message))
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        try:
            pipe.execute()
            self.logger.debug(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)

    def _bulk_publish_timed(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        total = 0
        pipe = self._producer.pipeline()
        for message in buffer:
            try:
                total += len(str(message).encode())
                pipe.publish(channel, serializer(message))
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        try:
            t1 = time()
            pipe.execute()
            t2 = time()
            self._flush_events.append(["bulk", t1, t2, t2 - t1, total])
            self.logger.debug(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)

    def liveness_test(self):
        """Get the livelyness of it."""
        try:
            response = self._producer.ping()
            if response:
                return True
            else:
                return False
        except ConnectionError as e:
            self.logger.exception(e)
            return False
        except Exception as e:
            self.logger.exception(e)
            return False
