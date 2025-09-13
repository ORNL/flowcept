"""MQ Redis Streams module.

This adapts the original Pub/Sub-based MQDaoRedis to use **Redis Streams** so data
can be consumed by tools like Grafana (via the Redis Data Source) and resiliently
processed with consumer groups.
"""

from __future__ import annotations

import os
import socket
from time import time, sleep
from typing import Callable, Dict, Any, List

import msgpack
import redis

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.daos.redis_conn import RedisConn
from flowcept.configs import (
    MQ_CHANNEL,
    MQ_HOST,
    MQ_PORT,
    MQ_PASSWORD,
    MQ_URI,
    MQ_SETTINGS,
    KVDB_ENABLED,
)


class MQDaoRedisStreams(MQDao):
    """MQ Redis class backed by **Redis Streams** instead of Pub/Sub.

    Key ideas
    ---------
    - Producers call :meth:`send_message` which now performs ``XADD`` into a stream
      (defaults to ``MQ_SETTINGS['stream_key']`` or ``MQ_CHANNEL``).
    - Consumers call :meth:`subscribe` and :meth:`message_listener`, which together
      use a Redis *consumer group* (``XGROUP``, ``XREADGROUP``) with blocking reads.
    - Successful handling results in ``XACK``. If ``message_handler`` returns ``False``,
      the message is *not* acknowledged so it can be retried.

    Config knobs (via MQ_SETTINGS)
    ------------------------------
    - ``stream_key``: str, name of the stream. Defaults to ``MQ_CHANNEL``.
    - ``stream_group``: str, consumer group name. Default: ``flowcept_cg``.
    - ``stream_consumer``: str, consumer name. Default: ``<hostname>-<pid>``.
    - ``stream_block_ms``: int, XREADGROUP BLOCK milliseconds. Default: 5000.
    - ``stream_count``: int, XREADGROUP COUNT per fetch. Default: 100.
    - ``stream_maxlen``: int, if >0, keep only approx this many entries (MAXLEN ~). Default: 0 (unbounded).
    - ``stream_field``: str, the field name used to store the serialized body. Default: ``body``.
    """

    # Pub/Sub-specific message types no longer apply, but we keep the constant for API compatibility.
    MESSAGE_TYPES_IGNORE = {"psubscribe"}

    def __init__(self, adapter_settings: Dict[str, Any] | None = None):
        super().__init__(adapter_settings)

        self._consumer_conn = None  # we use the same connection for producer/consumer
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

        # Streams config
        self.stream_key: str = MQ_SETTINGS.get("stream_key") or (MQ_CHANNEL or "flowcept:stream")
        # If user had a Pub/Sub pattern like "flowcept:*", sanitize it for a stream key
        if "*" in self.stream_key or "?" in self.stream_key:
            self.stream_key = self.stream_key.replace("*", ":all").replace("?", ":any")

        self.group: str = MQ_SETTINGS.get("stream_group", "flowcept_cg")
        self.consumer: str = MQ_SETTINGS.get("stream_consumer") or f"{socket.gethostname()}-{os.getpid()}"
        self.block_ms: int = int(MQ_SETTINGS.get("stream_block_ms", 5000))
        self.count: int = int(MQ_SETTINGS.get("stream_count", 100))
        self.maxlen: int = int(MQ_SETTINGS.get("stream_maxlen", 0))
        self.field: str = MQ_SETTINGS.get("stream_field", "body")

        self._stop = False

    # ---------------------------
    # Consumer (group) lifecycle
    # ---------------------------
    def subscribe(self):
        """Prepare consumer-group subscription on the stream (idempotent).

        Creates the stream and consumer group if they do not exist.
        """
        # Create group with $ so we only get *new* messages for this group
        try:
            self._producer.xgroup_create(name=self.stream_key, groupname=self.group, id="$", mkstream=True)
            self.logger.info(f"Created consumer group '{self.group}' on stream '{self.stream_key}' starting at '$'.")
        except redis.exceptions.ResponseError as e:
            # BUSYGROUP means the group already exists -> fine
            if "BUSYGROUP" in str(e):
                self.logger.debug(f"Consumer group '{self.group}' already exists on '{self.stream_key}'.")
            else:
                raise
        self._stop = False

    def unsubscribe(self):
        """Signal the listener loop to stop. Streams have no server-side unsubscribe."""
        self._stop = True

    def message_listener(self, message_handler: Callable[[Dict[str, Any]], bool]):
        """Blocking listener that reads from the consumer group and calls ``message_handler``.

        Returning ``True`` from ``message_handler`` acknowledges the message. Returning ``False``
        stops the loop *without* acknowledging the in-flight message (so it can be retried).
        """
        max_retrials = 10
        current_trials = 0

        while not self._stop and current_trials < max_retrials:
            try:
                # Blocking group read
                resp = self._producer.xreadgroup(
                    groupname=self.group,
                    consumername=self.consumer,
                    streams={self.stream_key: ">"},
                    count=self.count,
                    block=self.block_ms,
                )

                if not resp:  # timeout tick
                    continue

                # resp is a list of (stream, [(id, {field: value, ...}), ...])
                for _stream, entries in resp:
                    for message_id, fields in entries:
                        try:
                            raw = fields.get(self.field)
                            if not isinstance(raw, (bytes, bytearray)):
                                self.logger.warning(
                                    f"Skipping message {message_id} with unexpected field type: {type(raw)}"
                                )
                                # Acknowledge to skip bad payloads
                                self._producer.xack(self.stream_key, self.group, message_id)
                                continue

                            msg_obj = msgpack.loads(raw, strict_map_key=False)
                            # self.logger.debug(f"Received stream msg {message_id}: {msg_obj}")
                            should_continue = message_handler(msg_obj)

                            if should_continue:
                                self._producer.xack(self.stream_key, self.group, message_id)
                            else:
                                # Do not ack so it can be retried later
                                self._stop = True
                                break
                        except Exception as e:
                            self.logger.error(f"Failed to process message {message_id}")
                            self.logger.exception(e)
                            # Do not ack so it can be retried
                            continue

                current_trials = 0

            except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
                current_trials += 1
                self.logger.critical(f"Redis connection lost: {e}. Reconnecting in 3 seconds...")
                sleep(3)
            except Exception as e:
                self.logger.exception(e)
                continue

    # ---------------------------
    # Producer API (XADD)
    # ---------------------------
    def send_message(self, message: Dict[str, Any], channel: str | None = None, serializer=msgpack.dumps):
        """Send a message to the Redis **Stream** using ``XADD``.

        Parameters
        ----------
        message : dict
            The payload to serialize and store under the configured field (default ``body``).
        channel : str | None
            Optional override for the stream key (kept for API compatibility with Pub/Sub). If ``None``,
            use ``self.stream_key``.
        serializer : Callable
            Function that converts ``message`` into ``bytes`` (default: ``msgpack.dumps``).
        """
        stream = channel or self.stream_key
        value = serializer(message)
        if self.maxlen > 0:
            # Approximate trim to bound memory
            self._producer.xadd(stream, {self.field: value}, maxlen=self.maxlen, approximate=True)
        else:
            self._producer.xadd(stream, {self.field: value})

    def _send_message_timed(self, message: Dict[str, Any], channel: str | None = None, serializer=msgpack.dumps):
        """Send the message using timing for performance evaluation."""
        t1 = time()
        self.send_message(message, channel, serializer)
        t2 = time()
        self._flush_events.append(["single", t1, t2, t2 - t1, len(str(message).encode())])

    def _bulk_publish(self, buffer: List[Dict[str, Any]], channel: str | None = None, serializer=msgpack.dumps):
        """Bulk send with a pipeline of ``XADD`` calls."""
        stream = channel or self.stream_key
        pipe = self._producer.pipeline()
        for message in buffer:
            try:
                value = serializer(message)
                if self.maxlen > 0:
                    pipe.xadd(stream, {self.field: value}, maxlen=self.maxlen, approximate=True)
                else:
                    pipe.xadd(stream, {self.field: value})
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        try:
            pipe.execute()
            self.logger.debug(f"Flushed {len(buffer)} msgs to stream '{stream}'!")
        except Exception as e:
            self.logger.exception(e)

    def _bulk_publish_timed(self, buffer: List[Dict[str, Any]], channel: str | None = None, serializer=msgpack.dumps):
        total = 0
        stream = channel or self.stream_key
        pipe = self._producer.pipeline()
        for message in buffer:
            try:
                enc = serializer(message)
                total += len(enc)
                if self.maxlen > 0:
                    pipe.xadd(stream, {self.field: enc}, maxlen=self.maxlen, approximate=True)
                else:
                    pipe.xadd(stream, {self.field: enc})
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        try:
            t1 = time()
            pipe.execute()
            t2 = time()
            self._flush_events.append(["bulk", t1, t2, t2 - t1, total])
            self.logger.debug(f"Flushed {len(buffer)} msgs to stream '{stream}'!")
        except Exception as e:
            self.logger.exception(e)

    # ---------------------------
    # Healthcheck
    # ---------------------------
    def liveness_test(self) -> bool:
        """Ping Redis to confirm connectivity."""
        try:
            response = self._producer.ping()
            return bool(response)
        except ConnectionError as e:
            self.logger.exception(e)
            return False
        except Exception as e:
            self.logger.exception(e)
            return False
