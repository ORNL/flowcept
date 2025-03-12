"""MQ base module."""

import csv
from abc import ABC, abstractmethod
from time import time
from typing import Union, List, Callable

import msgpack

import flowcept.commons
from flowcept.commons.autoflush_buffer import AutoflushBuffer

from flowcept.commons.daos.keyvalue_dao import KeyValueDAO

from flowcept.commons.utils import chunked
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    MQ_CHANNEL,
    JSON_SERIALIZER,
    MQ_BUFFER_SIZE,
    MQ_INSERTION_BUFFER_TIME,
    MQ_CHUNK_SIZE,
    MQ_TYPE,
)

from flowcept.commons.utils import GenericJSONEncoder


class MQDao(ABC):
    """MQ base class."""

    ENCODER = GenericJSONEncoder if JSON_SERIALIZER == "complex" else None
    # TODO we don't have a unit test to cover complex dict!

    @staticmethod
    def build(*args, **kwargs) -> "MQDao":
        """Build it."""
        if MQ_TYPE == "redis":
            from flowcept.commons.daos.mq_dao.mq_dao_redis import MQDaoRedis

            return MQDaoRedis(*args, **kwargs)
        elif MQ_TYPE == "kafka":
            from flowcept.commons.daos.mq_dao.mq_dao_kafka import MQDaoKafka

            return MQDaoKafka(*args, **kwargs)
        elif MQ_TYPE == "mofka":
            from flowcept.commons.daos.mq_dao.mq_dao_mofka import MQDaoMofka

            return MQDaoMofka(*args, **kwargs)
        else:
            raise NotImplementedError

    @staticmethod
    def _get_set_name(exec_bundle_id=None):
        """Get the set name.

        :param exec_bundle_id: A way to group one or many interceptors, and
         treat each group as a bundle to control when their time_based
         threads started and ended.
        :return:
        """
        set_id = "started_mq_thread_execution"
        if exec_bundle_id is not None:
            set_id += "_" + str(exec_bundle_id)
        return set_id

    def __init__(self, adapter_settings=None):
        self.logger = FlowceptLogger()

        self._adapter_settings = adapter_settings
        self._keyvalue_dao = KeyValueDAO()
        self._time_based_flushing_started = False
        self.buffer: Union[AutoflushBuffer, List] = None
        self._flush_events = []

    @abstractmethod
    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        raise NotImplementedError()

    def bulk_publish(self, buffer):
        """Publish it."""
        # self.logger.info(f"Going to flush {len(buffer)} to MQ...")
        if MQ_CHUNK_SIZE > 1:
            for chunk in chunked(buffer, MQ_CHUNK_SIZE):
                self._bulk_publish(chunk)
        else:
            self._bulk_publish(buffer)

    def register_time_based_thread_init(self, interceptor_instance_id: str, exec_bundle_id=None):
        """Register the time."""
        set_name = MQDao._get_set_name(exec_bundle_id)
        # self.logger.info(
        #     f"Register start of time_based MQ flush thread {set_name}.{interceptor_instance_id}"
        # )
        self._keyvalue_dao.add_key_into_set(set_name, interceptor_instance_id)

    def register_time_based_thread_end(self, interceptor_instance_id: str, exec_bundle_id=None):
        """Register time."""
        set_name = MQDao._get_set_name(exec_bundle_id)
        self.logger.info(f"Registering end of time_based MQ flush thread {set_name}.{interceptor_instance_id}")
        self._keyvalue_dao.remove_key_from_set(set_name, interceptor_instance_id)
        self.logger.info(f"Done registering time_based MQ flush thread {set_name}.{interceptor_instance_id}")

    def all_time_based_threads_ended(self, exec_bundle_id=None):
        """Get all time."""
        set_name = MQDao._get_set_name(exec_bundle_id)
        return self._keyvalue_dao.set_is_empty(set_name)

    def set_campaign_id(self, campaign_id=None):
        """
        Set the current campaign ID in the key-value store.

        This method updates the "current_campaign_id" key in the key-value storage
        with the provided campaign ID.

        Parameters
        ----------
        campaign_id : str or None, optional
            The campaign ID to be set. If None, the key will be updated with a None value.

        Returns
        -------
        None
        """
        self._keyvalue_dao.set_key_value("current_campaign_id", campaign_id)

    def delete_current_campaign_id(self):
        """
        Delete current campaign id.
        """
        self._keyvalue_dao.delete_key("current_campaign_id")

    def init_buffer(self, interceptor_instance_id: str, exec_bundle_id=None):
        """Create the buffer."""
        if flowcept.configs.DB_FLUSH_MODE == "online":
            # msg = "Starting MQ time-based flushing! bundle: "
            # self.logger.debug(msg+f"{exec_bundle_id}; interceptor id: {interceptor_instance_id}")
            self.buffer = AutoflushBuffer(
                max_size=MQ_BUFFER_SIZE,
                flush_interval=MQ_INSERTION_BUFFER_TIME,
                flush_function=self.bulk_publish,
            )
            self.register_time_based_thread_init(interceptor_instance_id, exec_bundle_id)
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
            self.bulk_publish(self.buffer)
            self.buffer = list()

    def stop(self, interceptor_instance_id: str, bundle_exec_id: int = None):
        """Stop it."""
        t1 = time()
        msg0 = "MQ publisher received stop signal! bundle: "
        self.logger.debug(msg0 + f"{bundle_exec_id}; interceptor id: {interceptor_instance_id}")
        self._close_buffer()
        msg = "Flushed MQ for last time! Send stop msg. bundle: "
        self.logger.debug(msg + f"{bundle_exec_id}; interceptor id: {interceptor_instance_id}")
        self._send_mq_dao_time_thread_stop(interceptor_instance_id, bundle_exec_id)
        t2 = time()

        self._flush_events.append(["final", t1, t2, t2 - t1, "n/a"])

        with open(f"{MQ_TYPE}_{interceptor_instance_id}_{MQ_TYPE}_flush_events.csv", "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["type", "start", "end", "duration", "size"])
            writer.writerows(self._flush_events)

        # lets consumer know when to stop
        # TODO: See if line 167 does this already. If not consider using self.send_document_inserter_stop.
        # self._producer.publish(MQ_CHANNEL, msgpack.dumps({"message": "stop-now"}))

    def _send_mq_dao_time_thread_stop(self, interceptor_instance_id, exec_bundle_id=None):
        # These control_messages are handled by the document inserter
        # TODO: these should be constants
        msg = {
            "type": "flowcept_control",
            "info": "mq_dao_thread_stopped",
            "interceptor_instance_id": interceptor_instance_id,
            "exec_bundle_id": exec_bundle_id,
        }
        # self.logger.info("Control msg sent: " + str(msg))
        self.send_message(msg)

    def send_document_inserter_stop(self):
        """Send the document."""
        # These control_messages are handled by the document inserter
        msg = {"type": "flowcept_control", "info": "stop_document_inserter"}
        self.send_message(msg)

    @abstractmethod
    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send a message."""
        raise NotImplementedError()

    @abstractmethod
    def message_listener(self, message_handler: Callable):
        """Get message listener."""
        raise NotImplementedError()

    @abstractmethod
    def subscribe(self):
        """Subscribe to the interception channel."""
        raise NotImplementedError()

    @abstractmethod
    def liveness_test(self) -> bool:
        """Check whether the base KV store's connection is ready. This is enough for Redis MQ too. Other MQs need
        further liveness implementation.
        """
        try:
            response = self._keyvalue_dao.redis_conn.ping()
            if response:
                return True
            else:
                return False
        except ConnectionError as e:
            self.logger.exception(e)
            return False
        except Exception as e:
            self.logger.exception(e)
            return False
