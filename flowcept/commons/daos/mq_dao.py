import concurrent
import concurrent.futures
from functools import partial
from multiprocessing import Pool, cpu_count
from queue import Queue
from typing import Union, List, Dict, Callable

import msgpack
from redis import Redis
from redis.client import PubSub
from time import time

import flowcept.commons
from flowcept.commons.daos.autoflush_buffer import AutoflushBuffer

from flowcept.commons.daos.keyvalue_dao import KeyValueDAO
from flowcept.commons.utils import perf_log, chunked
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
    REDIS_PASSWORD,
    JSON_SERIALIZER,
    REDIS_BUFFER_SIZE,
    REDIS_INSERTION_BUFFER_TIME,
    REDIS_CHUNK_SIZE,
    PERF_LOG,
    REDIS_URI,
    ENRICH_MESSAGES,
    DB_FLUSH_MODE,
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

    @staticmethod
    def pipe_publish(
        buffer, redis_connection, logger=flowcept.commons.logger
    ):
        pipe = redis_connection.pipeline()
        logger.info(f"Going to flush {len(buffer)} to MQ...")
        for message in buffer:
            try:
                logger.debug(
                    f"Going to send Message:"
                    f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
                )
                pipe.publish(REDIS_CHANNEL, msgpack.dumps(message))
            except Exception as e:
                logger.exception(e)
                logger.error(
                    "Some messages couldn't be flushed! Check the messages' contents!"
                )
                logger.error(f"Message that caused error: {message}")
        t0 = 0
        if PERF_LOG:
            t0 = time()
        try:
            pipe.execute()
            logger.info(f"Flushed {len(buffer)} msgs to MQ!")
        except Exception as e:
            logger.exception(e)
        perf_log("mq_pipe_execute", t0)

    @staticmethod
    def bulk_publish(
        buffer, redis_connection, logger=flowcept.commons.logger
    ):
        if REDIS_CHUNK_SIZE > 1:
            for chunk in chunked(buffer, REDIS_CHUNK_SIZE):
                MQDao.pipe_publish(chunk, redis_connection, logger)
        else:
            MQDao.pipe_publish(buffer, redis_connection, logger)

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

        self._time_based_flushing_started = False
        self.buffer: Union[AutoflushBuffer, List] = None

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

    # def delete_all_time_based_threads_sets(self):
    #     return self._keyvalue_dao.delete_all_matching_sets(
    #         MQFlusher._get_set_name() + "*"
    #     )

    def init_buffer(self, interceptor_instance_id: str, exec_bundle_id=None):
        if flowcept.configs.DB_FLUSH_MODE == "online":
            self.logger.info(
                f"Starting MQ time-based flushing! bundle: {exec_bundle_id}; interceptor id: {interceptor_instance_id}"
            )
            self.buffer = AutoflushBuffer(
                max_size=REDIS_BUFFER_SIZE,
                flush_interval=REDIS_INSERTION_BUFFER_TIME,
                flush_function=MQDao.bulk_publish,
                redis_connection=self._redis,
            )
            #
            self.register_time_based_thread_init(
                interceptor_instance_id, exec_bundle_id
            )
            self._time_based_flushing_started = True
        else:
            self.buffer = list()

    def _close_buffer(self):
        if flowcept.configs.DB_FLUSH_MODE == "online":
            if self._time_based_flushing_started:
                self.buffer.stop()
                self._time_based_flushing_started = False
            else:
                self.logger.error("MQ time-based flushing is not started")
        else:
            MQDao.bulk_publish(self.buffer, self._redis)
            self.buffer = list()

    def subscribe(self) -> PubSub:
        pubsub = self._redis.pubsub()
        pubsub.psubscribe(REDIS_CHANNEL)
        return pubsub

    def stop(self, interceptor_instance_id: str, bundle_exec_id: int = None):
        self.logger.info(
            f"MQ publisher received stop signal! bundle: {bundle_exec_id}; interceptor id: {interceptor_instance_id}"
        )
        self._close_buffer()
        self.logger.info(
            f"Flushed MQ for the last time! Now going to send stop msg. bundle: {bundle_exec_id}; interceptor id: {interceptor_instance_id}"
        )
        self.send_mq_dao_time_thread_stop(
            interceptor_instance_id, bundle_exec_id
        )

    def send_mq_dao_time_thread_stop(
        self, interceptor_instance_id, exec_bundle_id=None
    ):
        # These control_messages are handled by the document inserter
        # TODO: these should be constants
        msg = {
            "type": "flowcept_control",
            "info": "mq_dao_thread_stopped",
            "interceptor_instance_id": interceptor_instance_id,
            "exec_bundle_id": exec_bundle_id,
        }
        self.logger.info("Control msg sent: " + str(msg))
        self._redis.publish(REDIS_CHANNEL, msgpack.dumps(msg))

    def send_document_inserter_stop(self):
        # These control_messages are handled by the document inserter
        msg = {"type": "flowcept_control", "info": "stop_document_inserter"}
        self._redis.publish(REDIS_CHANNEL, msgpack.dumps(msg))
