import uuid
from typing import Callable

import msgpack
from time import time

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.utils import perf_log

#from pymargo.core import Engine
import mochi.mofka.client as mofka
from mochi.mofka.client import ThreadPool, AdaptiveBatchSize
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

    _driver = mofka.MofkaDriver(MQ_SETTINGS.get("group_file", None), use_progress_thread=True)
    _TOPIC_NAME = MQ_SETTINGS.get("channel", None)
    _topic = _driver.open_topic(MQ_SETTINGS["channel"])

    def __init__(self,
                 kv_host=None, kv_port=None, adapter_settings=None, with_producer=True):
        super().__init__(kv_host=kv_host, kv_port=kv_port, adapter_settings=adapter_settings)
        self.producer = None
        if with_producer:
            print("Starting producer")
            self.producer = MQDaoMofka._topic.producer("p" + MQDaoMofka._TOPIC_NAME,
                                                       batch_size=mofka.AdaptiveBatchSize,
                                                       thread_pool=mofka.ThreadPool(1),
                                                       ordering=mofka.Ordering.Strict)
            #self.producer = self.topic.producer()

    def subscribe(self):
        #self.consumer = self.topic.consumer(name=self._mofka_conf["topic_name"]+str(uuid.uuid4()))
        batch_size = AdaptiveBatchSize
        thread_pool = ThreadPool(0)
        self.consumer = MQDaoMofka._topic.consumer(
            name=MQDaoMofka._TOPIC_NAME+str(uuid.uuid4()),
            thread_pool=thread_pool,
            batch_size=batch_size,
            data_selector=data_selector,
            data_broker=data_broker
        )

    def message_listener(self, message_handler: Callable):
        print("in message listener")
        try:
            while True:
                print("in message listner loop", flush=True)
                from time import sleep
                sleep(1)

                # I commented out these below to see what happens. The code gets stuck in the flush
                #event = self.consumer.pull().wait()
                # future = self.consumer.pull()
                # print("Got future", str(future))
                # #messages = [msgpack.loads(event.data[i].value(), raw=False) for i in range(len(event.data))]
                # event = future.wait()
                # print("Got future event", str(event))
                # metadata = json.loads(event.metadata)
                # self.logger.debug(f"Received message: {metadata}")
                # if not message_handler(metadata):
                #     break
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
            print("Sent buffer!!!")

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
            print("Now flushing buffer!!!")
            self.producer.flush()
            print("Flushed!!!")
            self.logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            self.logger.exception(e)
        perf_log("mq_pipe_flush", t0)
        print("done sending")
    def liveness_test(self):
        return True

