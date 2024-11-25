from typing import Callable

import msgpack
from time import time

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.utils import perf_log

#from pymargo.core import Engine
import mochi.mofka.client as mofka
from flowcept.configs import (
    MQ_CHANNEL,
    PERF_LOG,
    MQ_SETTINGS
    )

import json
def data_selector(metadata, descriptor):
    return descriptor

def data_broker(metadata, descriptor):
    return [bytearray(descriptor.size)]

class MQDaoMofka(MQDao):
    def __init__(self,
                #  mofka_protocol: str = MQ_SETTINGS["mofka_protocol"],
                #  group_file: str = MQ_SETTINGS["group_file"],
                #  topic_name: MQ_CHANNEL = "flowcept",
                 kv_host=None, kv_port=None, adapter_settings=None):
        super().__init__(kv_host=None, kv_port=None, adapter_settings=None)
        self._mofka_conf = {
            "group_file": "mofka.json",
            "topic_name": "flowcept"
        }

        print("In init", self._mofka_conf)
        #self._engine = Engine(self._mofka_conf["protocol"])
        self._driver = mofka.MofkaDriver(self._mofka_conf["group_file"])
        print("after driver created ")


    def producer(self):
        print("in producer ")
        if not (self._driver.topic_exists(self._mofka_conf["topic_name"])):
            topic = self._driver.create_topic(self._mofka_conf["topic_name"])
            self._driver.add_memory_partition(self._mofka_conf["topic_name"], 0)
        print("after topic creation ")
        topic = self._driver.open_topic(self._mofka_conf["topic_name"])
        producer = topic.producer("producer_"+self._mofka_conf["topic_name"],
                                        batch_size=mofka.AdaptiveBatchSize,
                                        thread_pool=mofka.ThreadPool(1),
                                        ordering=mofka.Ordering.Strict)
        return producer

    def consumer(self):
        print("")
        if not (self._driver.topic_exists(self._mofka_conf["topic_name"])):
            topic = self._driver.create_topic(self._mofka_conf["topic_name"])
            self._driver.add_memory_partition(self._mofka_conf["topic_name"], 0)
        print("after topic creation ")
        consumer = topic.consumer(name="consumer_"+self._mofka_conf["topic_name"],
                            thread_pool=mofka.ThreadPool(0),
                            batch_size=mofka.AdaptiveBatchSize,
                            data_selector=data_selector,
                            data_broker=data_broker)
        return consumer

    def message_listener(self, message_handler: Callable):
        consumer = self.consumer()
        try:
            while True:
                print("in message listner loop", flush=True)
                event = consumer.pull().wait()
                #messages = [msgpack.loads(event.data[i].value(), raw=False) for i in range(len(event.data))]
                metadata = json.loads(event.metadata)
                self.logger.debug(f"Received message: {metadata}")
                if not message_handler(metadata):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            del consumer


    def send_message(
        self, message: dict
    ):
        producer = self.producer()
        print("here in send msg", message, flush=True)
        producer.push(metadata=message) # using metadata to send data
        producer.flush()

    def _bulk_publish(
        self, buffer, serializer=msgpack.dump
    ):
        producer = self.producer()
        print("in bulk msg", flush=True)
        try:
            self.logger.debug(
                f"Going to send Message:"
                f"\n\t[BEGIN_MSG]{buffer}\n[END_MSG]\t"
            )
            print("buffer", type(buffer[0]))
            [producer.push(m) for m in buffer]

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
            producer.flush()
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)
        perf_log("mq_pipe_flush", t0)

    def liveness_test(self):
        return True
