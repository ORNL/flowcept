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
                kv_host=None, kv_port=None, adapter_settings=None, consume=False):
        super().__init__(kv_host=None, kv_port=None, adapter_settings=None)
        self._mofka_conf = {
            "group_file": "mofka.json",
            "topic_name": "flowcept"
        }

        print("In init", self._mofka_conf)
        self._driver = mofka.MofkaDriver(self._mofka_conf["group_file"], True)
        print("after driver created ")
        if not (self._driver.topic_exists(self._mofka_conf["topic_name"])):
            self._driver.create_topic(self._mofka_conf["topic_name"])
            self._driver.add_memory_partition(self._mofka_conf["topic_name"], 0)
        topic = self._driver.open_topic(self._mofka_conf["topic_name"])
        print("consumer value", consume)
        if not consume:
            print("before producer creation")
            self.producer = topic.producer("producer_"+self._mofka_conf["topic_name"],
                                            batch_size=mofka.AdaptiveBatchSize,
                                            thread_pool=mofka.ThreadPool(1),
                                            ordering=mofka.Ordering.Strict)
        else:
            print("create consumer")
            self.consumer = topic.consumer(name="consumer",
                                 thread_pool=mofka.ThreadPool(1))


    def message_listener(self, message_handler: Callable):
        print("in message listener")
        try:
            while True:
                print("in message listner loop", flush=True)
                event = self.consumer.pull().wait()
                #messages = [msgpack.loads(event.data[i].value(), raw=False) for i in range(len(event.data))]
                metadata = json.loads(event.metadata)
                self.logger.debug(f"Received message: {metadata}")
                if not message_handler(metadata):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            pass

    def send_message(
        self, message: dict
    ):
        print("in send msg", message, flush=True)
        self.producer.push(metadata=message) # using metadata to send data
        self.producer.flush()

    def _bulk_publish(
        self, buffer, serializer=msgpack.dump
    ):

        print("in bulk msg", flush=True)
        try:
            self.logger.debug(
                f"Going to send Message:"
                f"\n\t[BEGIN_MSG]{buffer}\n[END_MSG]\t"
            )
            print("buffer", type(buffer[0]))
            [self.producer.push(m) for m in buffer]

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
            self.producer.flush()
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)
        perf_log("mq_pipe_flush", t0)
        print("done sending")
    def liveness_test(self):
        return True
