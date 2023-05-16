import json
from redis import Redis
from redis.client import PubSub
from threading import Thread, Lock
from time import time, sleep

from flowcept.commons.utils import perf_log
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
    JSON_SERIALIZER,
    REDIS_BUFFER_SIZE,
    REDIS_INSERTION_BUFFER_TIME,
    PERF_LOG
)

from flowcept.commons.utils import GenericJSONEncoder


class MQDao:
    MESSAGE_TYPES_IGNORE = {"psubscribe"}
    ENCODER = GenericJSONEncoder if JSON_SERIALIZER == "complex" else None
    # TODO we don't have a unit test to cover complex dict!

    def __init__(self):
        self.logger = FlowceptLogger().get_logger()
        self._redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)
        self._buffer = list()
        self._time_thread: Thread = None
        self._previous_time = time()
        self._stop_flag = False
        self._start()
        self._lock = Lock()

    def _start(self):
        self._time_thread = Thread(
            target=self.time_based_flushing
        )
        self._time_thread.start()

    def stop(self):
        self._stop_flag = True
        self._time_thread.join()
        self._flush()
        self.logger.info("MQ listener stopped.")

    def _flush(self):
        if len(self._buffer):
            with self._lock:
                pipe = self._redis.pipeline()
                for message in self._buffer:
                    pipe.publish(REDIS_CHANNEL,
                                        json.dumps(message, cls=MQDao.ENCODER))
                t0 = 0
                if PERF_LOG:
                    t0 = time()
                pipe.execute()
                perf_log("mq_pipe_execute", t0)
                self.logger.debug(f"Flushed {len(self._buffer)} msgs to Redis!")
                self._buffer = list()

    def subscribe(self) -> PubSub:
        pubsub = self._redis.pubsub()
        pubsub.psubscribe(REDIS_CHANNEL)
        return pubsub

    def publish(self, message: dict):
        self._buffer.append(message)
        if len(self._buffer) >= REDIS_BUFFER_SIZE:
            self.logger.debug("Redis buffer exceeded, flushing...")
            self._flush()

    def time_based_flushing(self):
        while not self._stop_flag:
            if len(self._buffer):
                now = time()
                timediff = now - self._previous_time
                if timediff >= REDIS_INSERTION_BUFFER_TIME:
                    self.logger.debug("Time to flush to redis!")
                    self._previous_time = now
                    self._flush()
            self.logger.debug(f"Time-based Redis inserter going to wait for {REDIS_INSERTION_BUFFER_TIME} s.")
            sleep(REDIS_INSERTION_BUFFER_TIME)

    def stop_document_inserter(self):
        msg = {"type": "flowcept_control", "info": "stop_document_inserter"}
        self._redis.publish(REDIS_CHANNEL, json.dumps(msg))
