import uuid
from typing import Callable

import msgpack
from time import time

from diaspora_stream.api import Driver, Validator

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.configs import MQ_SETTINGS, MQ_CHANNEL


class MQDaoDiaspora(MQDao):
    """Main class to communicate with diaspora."""

    driver_options = {
        "root_path": "/tmp/diaspora-data/",
    }
    _validator = Validator.from_metadata()
    _driver = Driver(backend="files", options=driver_options)
    _topic = _driver.open_topic(MQ_SETTINGS["channel"])

    def __init__(self, adapter_settings=None, with_producer=True):
        super().__init__(adapter_settings=adapter_settings)
        self.producer = None
        if with_producer:
            producer_name = "p" + MQ_CHANNEL + "-" + str(uuid.uuid4())[:8]
            print(f"Starting producer {producer_name}")
            self.producer = MQDaoDiaspora._topic.producer(producer_name)

    def subscribe(self):
        """Subscribe to Diaspora topic."""
        self.consumer = MQDaoDiaspora._topic.consumer(name=MQ_CHANNEL + str(uuid.uuid4()))

    def message_listener(self, message_handler: Callable):
        """Diaspora's Message listener."""
        try:
            while True:
                future = self.consumer.pull()
                event = future.wait(timeout_ms=1)
                while not future.completed:
                    event = future.wait(timeout_ms=1)
                message = event.metadata
                self.logger.debug(f"Received message: {message}")
                if not message_handler(message):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            pass

    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send a single message to Diaspora."""
        self.producer.push(metadata=message)  # using metadata to send data
        self.producer.flush()

    def _send_message_timed(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        t1 = time()
        self.send_message(message, channel, serializer)
        t2 = time()
        self._flush_events.append(["single", t1, t2, t2 - t1, len(str(message).encode())])

    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        try:
            for m in buffer:
                self.producer.push(metadata=m)
        except Exception as e:
            self.logger.exception(e)
            self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
            self.logger.error(f"Message that caused error: {buffer}")
        try:
            self.producer.flush()
        except Exception as e:
            self.logger.exception(e)

    def _bulk_publish_timed(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        total = 0
        try:
            for m in buffer:
                self.producer.push(metadata=m)
                total += len(str(m).encode())

        except Exception as e:
            self.logger.exception(e)
            self.logger.error("Some messages couldn't be flushed! Check the messages' contents!")
            self.logger.error(f"Message that caused error: {buffer}")
        try:
            t1 = time()
            self.producer.flush()
            t2 = time()
            self._flush_events.append(["bulk", t1, t2, t2 - t1, total])
            # self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)

    def liveness_test(self):
        """Test Diaspora Liveness."""
        return True

    def unsubscribe(self):
        """Unsubscribes from Diaspora topic."""
        raise NotImplementedError()
