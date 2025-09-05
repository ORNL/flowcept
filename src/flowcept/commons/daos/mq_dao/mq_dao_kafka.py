"""MQ kafka module."""

from typing import Callable
from time import time
import msgpack

from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.admin import AdminClient

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.configs import (
    MQ_CHANNEL,
    MQ_HOST,
    MQ_PORT,
)


class MQDaoKafka(MQDao):
    """MQ kafka class."""

    def __init__(self, adapter_settings=None):
        super().__init__(adapter_settings)

        self._kafka_conf = {
            "bootstrap.servers": f"{MQ_HOST}:{MQ_PORT}",
        }
        self._producer = Producer(self._kafka_conf)
        self._consumer = None

    def subscribe(self):
        """Subscribe to the interception channel."""
        self._kafka_conf.update(
            {
                "group.id": "my_group",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
        )
        self._consumer = Consumer(self._kafka_conf)
        self._consumer.subscribe([MQ_CHANNEL])

    def message_listener(self, message_handler: Callable):
        """Get message listener."""
        try:
            while True:
                msg = self._consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        self.logger.error(f"Consumer error: {msg.error()}")
                        break
                message = msgpack.loads(msg.value(), raw=False, strict_map_key=False)
                self.logger.debug(f"Received message: {message}")
                if not message_handler(message):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            self._consumer.close()

    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send the message."""
        self._producer.produce(channel, key=channel, value=serializer(message))
        self._producer.flush()

    def _send_message_timed(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        t1 = time()
        self.send_message(message, channel, serializer)
        t2 = time()
        self._flush_events.append(["single", t1, t2, t2 - t1, len(str(message).encode())])

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        for message in buffer:
            try:
                self._producer.produce(channel, key=channel, value=serializer(message))
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        try:
            self._producer.flush()
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)

    def _bulk_publish_timed(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        total = 0
        for message in buffer:
            try:
                self._producer.produce(channel, key=channel, value=serializer(message))
                total += len(str(message).encode())
            except Exception as e:
                self.logger.exception(e)
                self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
                self.logger.error(f"Message that caused error: {message}")
        try:
            t1 = time()
            self._producer.flush()
            t2 = time()
            self._flush_events.append(["bulk", t1, t2, t2 - t1, total])
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)

    def liveness_test(self):
        """Get the livelyness of it."""
        try:
            admin_client = AdminClient(self._kafka_conf)
            kafka_metadata = admin_client.list_topics(timeout=5)
            return MQ_CHANNEL in kafka_metadata.topics
        except Exception as e:
            self.logger.exception(e)
            return False

    def unsubscribe(self):
        """Unsubscribes from Kafka topic and closes consumer if open."""
        if self._consumer is None:
            self.logger.warning("No Kafka consumer to unsubscribe.")
            return

        try:
            self._consumer.unsubscribe()
            self.logger.info("Unsubscribed from Kafka topics.")
        except RuntimeError as e:
            self.logger.debug(f"Consumer already closed while unsubscribing: {e}")
        except Exception as e:
            self.logger.exception(f"Error while unsubscribing from Kafka: {e}")
        finally:
            try:
                self._consumer.close()
            except Exception as e:
                self.logger.debug(f"Error closing consumer after unsubscribe: {e}")
            self._consumer = None
