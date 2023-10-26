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
    REDIS_PASSWORD,
    REDIS_STARTED_MQ_THREADS_KEY,
    JSON_SERIALIZER,
    REDIS_BUFFER_SIZE,
    REDIS_INSERTION_BUFFER_TIME,
    PERF_LOG,
)

from flowcept.commons.utils import GenericJSONEncoder


class MQDao:
    MESSAGE_TYPES_IGNORE = {"psubscribe"}
    ENCODER = GenericJSONEncoder if JSON_SERIALIZER == "complex" else None
    # TODO we don't have a unit test to cover complex dict!

    def __init__(self):
        self.logger = FlowceptLogger().get_logger()
        self._redis = Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=0, password=REDIS_PASSWORD
        )
        self._buffer = None
        self._time_thread: Thread = None
        self._previous_time = -1
        self._stop_flag = False
        self._time_based_flushing_started = False
        self._lock = None

    def start_time_based_flushing(self):
        self._buffer = list()
        self._time_thread: Thread = None
        self._previous_time = time()
        self._stop_flag = False
        self._time_based_flushing_started = False
        self._lock = Lock()

        self._time_thread = Thread(target=self.time_based_flushing)
        self._redis.incr(REDIS_STARTED_MQ_THREADS_KEY)
        self.logger.debug(
            f"Incrementing REDIS_STARTED_MQ_THREADS_KEY. Now: {self.get_started_mq_threads()}"
        )
        self._time_based_flushing_started = True
        self._time_thread.start()

    def get_started_mq_threads(self):
        return int(self._redis.get(REDIS_STARTED_MQ_THREADS_KEY))

    def reset_started_mq_threads(self):
        self.logger.debug("RESETTING REDIS_STARTED_MQ_THREADS_KEY TO 0")
        self._redis.set(REDIS_STARTED_MQ_THREADS_KEY, 0)

    def stop(self):
        self.logger.info("MQ time-based received stop signal!")
        if self._time_based_flushing_started:
            self._stop_flag = True
            self._time_thread.join()
            self._flush()
            self._send_stop_message()
            self._time_based_flushing_started = False
            self.logger.info("MQ time-based flushing stopped.")
        else:
            self.logger.warning("MQ time-based flushing is not started")

    def _flush(self):
        with self._lock:
            if len(self._buffer):
                pipe = self._redis.pipeline()
                for message in self._buffer:
                    pipe.publish(
                        REDIS_CHANNEL, json.dumps(message, cls=MQDao.ENCODER)
                    )
                t0 = 0
                if PERF_LOG:
                    t0 = time()
                pipe.execute()
                perf_log("mq_pipe_execute", t0)
                self.logger.debug(
                    f"Flushed {len(self._buffer)} msgs to Redis!"
                )
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
            self.logger.debug(
                f"Time-based Redis inserter going to wait for {REDIS_INSERTION_BUFFER_TIME} s."
            )
            sleep(REDIS_INSERTION_BUFFER_TIME)

    def _send_stop_message(self):
        # TODO: these should be constants
        msg = {"type": "flowcept_control", "info": "mq_dao_thread_stopped"}
        self._redis.publish(REDIS_CHANNEL, json.dumps(msg))

    def stop_document_inserter(self):
        msg = {"type": "flowcept_control", "info": "stop_document_inserter"}
        self._redis.publish(REDIS_CHANNEL, json.dumps(msg))
