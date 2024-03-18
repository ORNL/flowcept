from typing import Union, List

import msgpack
from redis import Redis
from redis.client import PubSub
from threading import Thread, Lock
from time import time, sleep

from flowcept.commons.daos.keyvalue_dao import KeyValueDAO
from flowcept.commons.utils import perf_log
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
    REDIS_PASSWORD,
    JSON_SERIALIZER,
    REDIS_BUFFER_SIZE,
    REDIS_INSERTION_BUFFER_TIME,
    PERF_LOG,
    REDIS_URI,
    ENRICH_MESSAGES,
)

from flowcept.commons.utils import GenericJSONEncoder


class MQDao:
    MESSAGE_TYPES_IGNORE = {"psubscribe"}
    ENCODER = GenericJSONEncoder if JSON_SERIALIZER == "complex" else None

    # TODO we don't have a unit test to cover complex dict!

    @staticmethod
    def _get_set_name(exec_bundle_id=None):
        """
        :param exec_bundle_id: A way to group one or many interceptors, and treat each group as a bundle to control when their time_based threads started and ended.
        :return:
        """
        set_id = f"started_mq_thread_execution"
        if exec_bundle_id is not None:
            set_id += "_" + str(exec_bundle_id)
        return set_id

    def __init__(self, mq_host=None, mq_port=None, adapter_settings=None):
        self.logger = FlowceptLogger()

        if REDIS_URI is not None:
            # If a URI is provided, use it for connection
            self._redis = Redis.from_url(REDIS_URI)
        else:
            # Otherwise, use the host, port, and password settings
            self._redis = Redis(
                host=REDIS_HOST if mq_host is None else mq_host,
                port=REDIS_PORT if mq_port is None else mq_port,
                db=0,
                password=REDIS_PASSWORD if REDIS_PASSWORD else None,
            )
        self._adapter_settings = adapter_settings
        self._keyvalue_dao = KeyValueDAO(connection=self._redis)
        self._buffer = None
        self._time_thread: Thread = None
        self._previous_time = -1
        self._stop_flag = False
        self._time_based_flushing_started = False
        self._lock = None

    def register_time_based_thread_init(
        self, interceptor_instance_id: str, exec_bundle_id=None
    ):
        set_name = MQDao._get_set_name(exec_bundle_id)
        self.logger.info(
            f"Registering the beginning of the time_based MQ flush thread {set_name}.{interceptor_instance_id}"
        )
        self._keyvalue_dao.add_key_into_set(set_name, interceptor_instance_id)

    def register_time_based_thread_end(
        self, interceptor_instance_id: str, exec_bundle_id=None
    ):
        set_name = MQDao._get_set_name(exec_bundle_id)
        self.logger.info(
            f"Registering the end of the time_based MQ flush thread {set_name}.{interceptor_instance_id}"
        )
        self._keyvalue_dao.remove_key_from_set(
            set_name, interceptor_instance_id
        )
        self.logger.info(
            f"Done registering the end of the time_based MQ flush thread {set_name}.{interceptor_instance_id}"
        )

    def all_time_based_threads_ended(self, exec_bundle_id=None):
        set_name = MQDao._get_set_name(exec_bundle_id)
        return self._keyvalue_dao.set_is_empty(set_name)

    def delete_all_time_based_threads_sets(self):
        return self._keyvalue_dao.delete_all_matching_sets(
            MQDao._get_set_name() + "*"
        )

    def start_time_based_flushing(
        self, interceptor_instance_id: str, exec_bundle_id=None
    ):
        self.logger.info(
            f"Starting MQ time-based flushing! bundle: {exec_bundle_id}; interceptor id: {interceptor_instance_id}"
        )
        self._buffer = list()  # Buffer(REDIS_BUFFER_SIZE+1)
        self._time_thread: Thread = None
        self._previous_time = time()
        self._stop_flag = False
        self._time_based_flushing_started = False
        self._lock = Lock()
        self._time_thread = Thread(target=self.time_based_flushing)
        self.register_time_based_thread_init(
            interceptor_instance_id, exec_bundle_id
        )
        self._time_based_flushing_started = True
        self._time_thread.start()

    def stop_time_based_flushing(
        self, interceptor_instance_id: str, exec_bundle_id: int = None
    ):
        self.logger.info(
            f"MQ time-based received stop signal! bundle: {exec_bundle_id}; interceptor id: {interceptor_instance_id}"
        )
        if self._time_based_flushing_started:
            self._stop_flag = True
            self._time_thread.join()
            self.logger.info(
                f"Joined MQ time thread. bundle: {exec_bundle_id}; interceptor id: {interceptor_instance_id}"
            )
            self._flush()
            self.logger.info(
                f"Flushed MQ for the last time! Now going to send stop msg. bundle: {exec_bundle_id}; interceptor id: {interceptor_instance_id}"
            )
            self._send_stop_message(interceptor_instance_id, exec_bundle_id)
            self._time_based_flushing_started = False
            self.logger.info(
                f"MQ time-based sent stop message! bundle: {exec_bundle_id}; interceptor id: {interceptor_instance_id}"
            )
        else:
            self.logger.error("MQ time-based flushing is not started")

    def _flush(self):
        if self._buffer is None:
            self.logger.error("This MQ has never been started!")
            return
        with self._lock:
            if len(self._buffer):
                pipe = self._redis.pipeline()
                self.logger.critical(
                    f"Going to flush {len(self._buffer)} to MQ..."
                )
                for message in self._buffer:
                    try:
                        if ENRICH_MESSAGES:
                            message.enrich(
                                adapter_settings=self._adapter_settings
                            )

                        self.logger.debug(
                            f"Going to send Message:"
                            f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
                        )

                        pipe.publish(  # no redis
                            REDIS_CHANNEL, message.serialize()
                        )
                        self.logger.info(
                            f"Flushed {len(self._buffer)} to MQ."
                        )
                    except Exception as e:
                        self.logger.exception(e)
                        self.logger.error(
                            "Some messages couldn't be flushed! Check the messages' contents!"
                        )
                        self.logger.error(
                            f"Message that caused error: {message}"
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

    def publish(self, message):
        # TODO: refactor we should have a parent MessageObject class
        self._buffer.append(message)
        if len(self._buffer) >= REDIS_BUFFER_SIZE:
            self.logger.critical("Redis buffer exceeded, flushing...")
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
            self.logger.info(
                f"Time-based Redis inserter going to wait for {REDIS_INSERTION_BUFFER_TIME} s."
            )
            sleep(REDIS_INSERTION_BUFFER_TIME)
        self.logger.info("Broke the time_based_flushing in mq!")

    def _send_stop_message(
        self, interceptor_instance_id, exec_bundle_id=None
    ):
        # TODO: these should be constants
        msg = {
            "type": "flowcept_control",
            "info": "mq_dao_thread_stopped",
            "interceptor_instance_id": interceptor_instance_id,
            "exec_bundle_id": exec_bundle_id,
        }
        self.logger.info("Control msg sent: " + str(msg))
        self._redis.publish(REDIS_CHANNEL, msgpack.dumps(msg))

    def stop_document_inserter(self):
        msg = {"type": "flowcept_control", "info": "stop_document_inserter"}
        self._redis.publish(REDIS_CHANNEL, msgpack.dumps(msg))
