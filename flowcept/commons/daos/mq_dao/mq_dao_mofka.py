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

    def subscribe(self):
        batch_size = AdaptiveBatchSize
        thread_pool = ThreadPool(0)
        self.consumer = MQDaoMofka._topic.consumer(
            name=MQDaoMofka._TOPIC_NAME+str(uuid.uuid4()),
            thread_pool=thread_pool,
            batch_size=batch_size
        )

    def message_listener(self, message_handler: Callable):
        try:
            while True:
                event = self.consumer.pull().wait()
                message = json.loads(event.metadata)
                self.logger.debug(f"Received message: {message}")
                if not message_handler(message):
                    break
        except Exception as e:
            self.logger.exception(e)
        finally:
            pass

    def send_message(
        self, message: dict
    ):
        self.producer.push(metadata=message) # using metadata to send data
        self.producer.flush()

    def _bulk_publish(
        self, buffer, serializer=msgpack.dump
    ):
        try:
            self.logger.debug(
                f"Going to send Message:"
                f"\n\t[BEGIN_MSG]{buffer}\n[END_MSG]\t"
            )
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
    def liveness_test(self):
        return True

