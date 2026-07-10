"""MQ RabbitMQ (AMQP) module using pika."""

from time import time
from typing import Callable

import msgpack
import pika

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.configs import MQ_CHANNEL, MQ_HOST, MQ_PORT, MQ_PASSWORD, MQ_USERNAME, MQ_VHOST


class MQDaoRabbitMQ(MQDao):
    """MQ DAO backed by RabbitMQ via AMQP (pika).

    Uses a **fanout exchange** named after :data:`MQ_CHANNEL` so every
    subscribed consumer receives every published message — the same
    pub/sub semantic used by the Redis and Kafka backends.

    A separate connection is maintained for publishing and subscribing so
    the two roles never share a single pika channel.
    """

    def __init__(self, adapter_settings=None):
        super().__init__(adapter_settings)
        credentials = pika.PlainCredentials(
            MQ_USERNAME or "guest",
            MQ_PASSWORD or "guest",
        )
        self._conn_params = pika.ConnectionParameters(
            host=MQ_HOST,
            port=MQ_PORT,
            virtual_host=MQ_VHOST,
            credentials=credentials,
            heartbeat=60,
            blocked_connection_timeout=300,
        )
        self._pub_connection = None
        self._pub_channel = None
        self._sub_connection = None
        self._sub_channel = None
        self._queue_name = None
        self._connect_producer()

    # ------------------------------------------------------------------
    # Producer helpers
    # ------------------------------------------------------------------

    def _connect_producer(self):
        """Open a fresh producer connection and declare the fanout exchange."""
        self._pub_connection = pika.BlockingConnection(self._conn_params)
        self._pub_channel = self._pub_connection.channel()
        self._pub_channel.exchange_declare(exchange=MQ_CHANNEL, exchange_type="fanout", durable=True)

    def _ensure_producer(self):
        """Re-connect the producer if the connection is closed or unhealthy."""
        try:
            if self._pub_connection and self._pub_connection.is_open:
                # Non-blocking I/O pass — keeps heartbeats alive.
                self._pub_connection.process_data_events(time_limit=0)
                return
        except Exception:
            pass
        self._connect_producer()

    # ------------------------------------------------------------------
    # MQDao interface
    # ------------------------------------------------------------------

    def subscribe(self):
        """Open a consumer connection, declare an exclusive auto-delete queue, and bind it."""
        self._sub_connection = pika.BlockingConnection(self._conn_params)
        self._sub_channel = self._sub_connection.channel()
        self._sub_channel.exchange_declare(exchange=MQ_CHANNEL, exchange_type="fanout", durable=True)
        result = self._sub_channel.queue_declare(queue="", exclusive=True)
        self._queue_name = result.method.queue
        self._sub_channel.queue_bind(exchange=MQ_CHANNEL, queue=self._queue_name)

    def unsubscribe(self):
        """Cancel the consumer and close the subscription connection."""
        try:
            if self._sub_channel and self._sub_channel.is_open:
                self._sub_channel.cancel()
        except Exception:
            pass
        try:
            if self._sub_connection and self._sub_connection.is_open:
                self._sub_connection.close()
        except Exception:
            pass
        self._sub_channel = None
        self._sub_connection = None
        self._queue_name = None

    def message_listener(self, message_handler: Callable):
        """Consume messages from the bound queue and forward them to *message_handler*.

        Exits when *message_handler* returns ``False`` (or raises).
        Always calls :meth:`unsubscribe` on exit.
        """
        try:
            for method_frame, _props, body in self._sub_channel.consume(
                self._queue_name,
                auto_ack=False,
                inactivity_timeout=1,
            ):
                if method_frame is None:
                    # Heartbeat tick — no message delivered; keep looping.
                    continue
                try:
                    msg_obj = msgpack.loads(body, strict_map_key=False)
                    keep_going = message_handler(msg_obj)
                    self._sub_channel.basic_ack(method_frame.delivery_tag)
                    if not keep_going:
                        break
                except Exception as e:
                    self.logger.error("Failed to process RabbitMQ message.")
                    self.logger.exception(e)
                    self._sub_channel.basic_nack(method_frame.delivery_tag, requeue=False)
        except Exception as e:
            self.logger.exception(e)
        finally:
            self.unsubscribe()

    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Publish a single message to the fanout exchange."""
        self._ensure_producer()
        self._pub_channel.basic_publish(
            exchange=channel,
            routing_key="",
            body=serializer(message),
        )

    def _send_message_timed(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Timed variant of :meth:`send_message`."""
        t1 = time()
        self.send_message(message, channel, serializer)
        t2 = time()
        self._flush_events.append(["single", t1, t2, t2 - t1, len(str(message).encode())])

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Publish all messages in *buffer* to the fanout exchange."""
        self._ensure_producer()
        for message in buffer:
            try:
                self._pub_channel.basic_publish(
                    exchange=channel,
                    routing_key="",
                    body=serializer(message),
                )
            except Exception as e:
                self.logger.exception(e)
                self.logger.error(f"Message could not be flushed: {message}")
        self.logger.debug(f"Flushed {len(buffer)} msgs to MQ!")

    def _bulk_publish_timed(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Timed variant of :meth:`_bulk_publish`."""
        total = 0
        self._ensure_producer()
        t1 = time()
        for message in buffer:
            try:
                total += len(str(message).encode())
                self._pub_channel.basic_publish(
                    exchange=channel,
                    routing_key="",
                    body=serializer(message),
                )
            except Exception as e:
                self.logger.exception(e)
                self.logger.error(f"Message could not be flushed: {message}")
        t2 = time()
        self._flush_events.append(["bulk", t1, t2, t2 - t1, total])
        self.logger.debug(f"Flushed {len(buffer)} msgs to MQ!")

    def liveness_test(self) -> bool:
        """Return True if the RabbitMQ broker is reachable."""
        try:
            conn = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=MQ_HOST,
                    port=MQ_PORT,
                    virtual_host=MQ_VHOST,
                    credentials=pika.PlainCredentials(
                        MQ_USERNAME or "guest",
                        MQ_PASSWORD or "guest",
                    ),
                    heartbeat=10,
                )
            )
            alive = conn.is_open
            conn.close()
            return alive
        except Exception as e:
            self.logger.exception(e)
            return False
