"""MQ kafka module."""

from typing import Callable

import msgpack
from time import time

from confluent_kafka import Producer, Consumer, KafkaError
from confluent_kafka.admin import AdminClient

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.utils import perf_log
from flowcept.configs import (
    MQ_CHANNEL,
    PERF_LOG,
    MQ_HOST,
    MQ_PORT,
)


class MQDaoKafka(MQDao):
    """MQ kafka class."""

    def __init__(self, kv_host=None, kv_port=None, adapter_settings=None):
        super().__init__(kv_host, kv_port, adapter_settings)

        self._kafka_conf = {
            "bootstrap.servers": f"{MQ_HOST}:{MQ_PORT}",
        }
        self._producer = Producer(self._kafka_conf)

    def message_listener(self, message_handler: Callable):
        """Get message listener."""
        self._kafka_conf.update(
            {
                "group.id": "my_group",
                "auto.offset.reset": "earliest",
                "enable.auto.commit": True,
            }
        )
        consumer = Consumer(self._kafka_conf)
        consumer.subscribe([MQ_CHANNEL])

        try:
            while True:
                msg = consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    else:
                        self.logger.error(f"Consumer error: {msg.error()}")
                        break
                message = msgpack.loads(msg.value(), raw=False)
                self.logger.debug(f"Received message: {message}")
                if not message_handler(message):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            consumer.close()

    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send the message."""
        self._producer.produce(channel, key=channel, value=serializer(message))
        self._producer.flush()

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        for message in buffer:
            try:
                self.logger.debug(
                    f"Going to send Message:" f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
                )
                self._producer.produce(channel, key=channel, value=serializer(message))
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
            self._producer.flush()
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)
        perf_log("mq_pipe_flush", t0)

    def liveness_test(self):
        """Get the livelyness of it."""
        try:
            super().liveness_test()
            admin_client = AdminClient(self._kafka_conf)
            kafka_metadata = admin_client.list_topics(timeout=5)
            return MQ_CHANNEL in kafka_metadata.topics
        except Exception as e:
            self.logger.exception(e)
            return False
