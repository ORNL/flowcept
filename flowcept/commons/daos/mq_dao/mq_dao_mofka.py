from typing import Callable

import msgpack
from time import time

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.utils import perf_log

from pymargo.core import Engine
import mochi.mofka.client as mofka
from flowcept.configs import (
    MQ_CHANNEL,
    PERF_LOG)

import json
def data_selector(metadata, descriptor):
    return descriptor

def data_broker(metadata, descriptor):
    return [bytearray(descriptor.size)]

class MQDaoMofka(MQDao):
    def __init__(self,
                 mofka_protocol: str,
                 group_file: str,
                 topic_name: MQ_CHANNEL = "flowcept"):
        self._mofka_conf = {
            "protocol": mofka_protocol,
            "group_file": group_file,
            "topic_name": topic_name
        }
        self._engine = Engine(self._mofka_conf["protocol"])
        self._driver = mofka.MofkaDriver(self._mofka_conf["group_file"], self._engine)
        if not (self._driver.topic_exists(self._mofka_conf["topic_name"])):
            topic = self._driver.create_topic(self._mofka_conf["topic_name"])
            self._driver.add_memory_partition(self._mofka_conf["topic_name"], 0)
        topic = self._driver.open_topic(topic_name)
        self._producer = topic.producer("producer_"+self._mofka_conf["topic_name"],
                                        batch_size=mofka.AdaptiveBatchSize,
                                        thread_pool=mofka.ThreadPool(1),
                                        ordering=mofka.Ordering.Strict)

    def message_listener(self, message_handler: Callable, topic_name: MQ_CHANNEL):
        if not (self._driver.topic_exists(topic_name)):
            self._driver.create_topic(topic_name)
            self._driver.add_memory_partition(topic_name, 0)

        topic = self._driver.open_topic(topic_name)
        consumer = topic.consumer(name="consumer_"+topic_name,
                                  thread_pool=mofka.ThreadPool(1),
                                  batch_size=mofka.AdaptiveBatchSize,
                                  data_selector=data_selector,
                                  data_broker=data_broker)
        try:
            while True:
                event = consumer.pull().wait()
                messages = [msgpack.loads(event.data[i].value(), raw=False) for i in range(len(event.data))]
                metadata = json.loads(event.metadata)
                self.logger.debug(f"Received message: {messages}")
                if not message_handler(messages):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            del consumer

    def send_message(
        self, message: dict
    ):
        self._producer.push(metadata=message, data=bytes()) # using metadata to send data
        self._producer.flush()

    def _bulk_publish(
        self, buffer, serializer=msgpack.dump
    ):
        try:
            self.logger.debug(
                f"Going to send Message:"
                f"\n\t[BEGIN_MSG]{buffer}\n[END_MSG]\t"
            )
            self._producer.push(metadata={"msg": "bulk"}  ,
                                data=[serializer(m) for m in buffer]
            )
        except Exception as e:
            self.logger.exception(e)
            self.logger.error(
                "Some messages couldn't be flushed! Check the messages' contents!"
            )
            self.logger.error(f"Message that caused error: {buffer}")
        t0 = 0
        if PERF_LOG:
            t0 = time()
        try:
            self._producer.flush()
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)
        perf_log("mq_pipe_flush", t0)
