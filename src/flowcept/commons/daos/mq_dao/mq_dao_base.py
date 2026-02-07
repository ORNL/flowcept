"""MQ base module."""

from abc import abstractmethod
from typing import Union, List, Callable
import csv
import msgpack
from time import time
import flowcept.commons
from flowcept.commons.autoflush_buffer import AutoflushBuffer
from flowcept.commons.daos.keyvalue_dao import KeyValueDAO
from flowcept.commons.utils import chunked, buffer_to_disk, resolve_dump_buffer_path
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    MQ_CHANNEL,
    JSON_SERIALIZER,
    MQ_BUFFER_SIZE,
    MQ_INSERTION_BUFFER_TIME,
    MQ_CHUNK_SIZE,
    MQ_TYPE,
    MQ_TIMING,
    KVDB_ENABLED,
    MQ_ENABLED,
    DUMP_BUFFER_PATH,
    APPEND_WORKFLOW_ID_TO_PATH,
    APPEND_ID_TO_PATH,
)

from flowcept.commons.utils import GenericJSONEncoder


class MQDao(object):
    """MQ base class."""

    ENCODER = GenericJSONEncoder if JSON_SERIALIZER == "complex" else None
    # TODO we don't have a unit test to cover complex dict!
    MQ_THREAD_SET_ID = "started_mq_thread_execution"
    MQ_FLUSH_COMPLETE_SET_ID = "pending_mq_flush_complete"

    @staticmethod
    def build(*args, **kwargs) -> "MQDao":
        """Build it."""
        if not MQ_ENABLED:
            return MQDao()

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

    def __init__(self, adapter_settings=None):
        self.logger = FlowceptLogger()
        self.started = False
        self._adapter_settings = adapter_settings
        if KVDB_ENABLED:
            from flowcept.commons.daos.keyvalue_dao import KeyValueDAO

            self._keyvalue_dao = KeyValueDAO()
        else:
            self._keyvalue_dao = None
        self._time_based_flushing_started = False
        self.buffer: Union[AutoflushBuffer, List] = None
        if MQ_TIMING:
            self._flush_events = []
            self.stop = self._stop_timed
            self.send_message = self._send_message_timed
            self._bulk_publish = self._bulk_publish_timed
        else:
            self.stop = self._stop

    @abstractmethod
    def _bulk_publish(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        raise NotImplementedError()

    def _bulk_publish_timed(self, buffer, channel=MQ_CHANNEL, serializer=msgpack.dumps):
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
        set_name = KeyValueDAO.get_set_name(MQDao.MQ_THREAD_SET_ID, exec_bundle_id)
        # self.logger.info(
        #     f"Register start of time_based MQ flush thread {set_name}.{interceptor_instance_id}"
        # )
        self._keyvalue_dao.add_key_into_set(set_name, interceptor_instance_id)
        flush_set_name = KeyValueDAO.get_set_name(MQDao.MQ_FLUSH_COMPLETE_SET_ID, exec_bundle_id)
        self._keyvalue_dao.add_key_into_set(flush_set_name, interceptor_instance_id)

    def register_time_based_thread_end(self, interceptor_instance_id: str, exec_bundle_id=None):
        """Register time."""
        set_name = KeyValueDAO.get_set_name(MQDao.MQ_THREAD_SET_ID, exec_bundle_id)
        self.logger.info(f"Registering end of time_based MQ flush thread {set_name}.{interceptor_instance_id}")
        self._keyvalue_dao.remove_key_from_set(set_name, interceptor_instance_id)
        self.logger.info(f"Done registering time_based MQ flush thread {set_name}.{interceptor_instance_id}")

    def all_time_based_threads_ended(self, exec_bundle_id=None):
        """Get all time."""
        set_name = KeyValueDAO.get_set_name(MQDao.MQ_THREAD_SET_ID, exec_bundle_id)
        return self._keyvalue_dao.set_is_empty(set_name)

    def register_flush_complete(self, interceptor_instance_id: str, exec_bundle_id=None):
        """Register a flush-complete signal for an interceptor."""
        set_name = KeyValueDAO.get_set_name(MQDao.MQ_FLUSH_COMPLETE_SET_ID, exec_bundle_id)
        self.logger.info(f"Registering flush completion {set_name}.{interceptor_instance_id}")
        self._keyvalue_dao.remove_key_from_set(set_name, interceptor_instance_id)
        self.logger.info(f"Done registering flush completion {set_name}.{interceptor_instance_id}")

    def all_flush_complete_received(self, exec_bundle_id=None):
        """Return True when all interceptors in the bundle reported flush completion."""
        set_name = KeyValueDAO.get_set_name(MQDao.MQ_FLUSH_COMPLETE_SET_ID, exec_bundle_id)
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

    def init_buffer(self, interceptor_instance_id: str, exec_bundle_id=None, check_safe_stops=True):
        """Create the buffer."""
        if not self.started:
            if flowcept.configs.DB_FLUSH_MODE == "online":
                self.buffer = AutoflushBuffer(
                    flush_function=self.bulk_publish,
                    max_size=MQ_BUFFER_SIZE,
                    flush_interval=MQ_INSERTION_BUFFER_TIME,
                )
                if check_safe_stops:
                    self.register_time_based_thread_init(interceptor_instance_id, exec_bundle_id)
                self._time_based_flushing_started = True
            else:
                self.buffer = list()
            self.started = True

    def _close_buffer(self):
        if flowcept.configs.DUMP_BUFFER_ENABLED and DUMP_BUFFER_PATH is not None:
            _buf = self.buffer.current_buffer if isinstance(self.buffer, AutoflushBuffer) else self.buffer
            dump_path = resolve_dump_buffer_path(
                DUMP_BUFFER_PATH,
                flowcept.Flowcept.current_workflow_id,
                APPEND_WORKFLOW_ID_TO_PATH,
                APPEND_ID_TO_PATH,
            )
            buffer_to_disk(_buf, dump_path, self.logger)

        if flowcept.configs.DB_FLUSH_MODE == "online":
            if self._time_based_flushing_started:
                self.buffer.stop()
                self._time_based_flushing_started = False
                self.logger.debug("MQ time-based flushed for the last time!")
            else:
                self.logger.error("MQ time-based flushing is not started")
        else:
            self.buffer = list()

        self.logger.debug("Buffer closed.")

    def _stop_timed(self, interceptor_instance_id: str, check_safe_stops: bool = True, bundle_exec_id: int = None):
        t1 = time()
        self._stop(interceptor_instance_id, check_safe_stops, bundle_exec_id)
        t2 = time()
        self._flush_events.append(["final", t1, t2, t2 - t1, "n/a"])

        with open(f"{MQ_TYPE}_{interceptor_instance_id}_{MQ_TYPE}_flush_events.csv", "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow(["type", "start", "end", "duration", "size"])
            writer.writerows(self._flush_events)

    def _stop(self, interceptor_instance_id: str = None, check_safe_stops: bool = True, bundle_exec_id: int = None):
        """Stop MQ publisher."""
        self._close_buffer()
        if check_safe_stops and MQ_ENABLED:
            self.logger.debug(
                f"Sending flush-complete msg. Bundle: {bundle_exec_id}; interceptor id: {interceptor_instance_id}"
            )
            self._send_mq_dao_flush_complete(interceptor_instance_id, bundle_exec_id)
            self.logger.debug(f"Sending stop msg. Bundle: {bundle_exec_id}; interceptor id: {interceptor_instance_id}")
            self._send_mq_dao_time_thread_stop(interceptor_instance_id, bundle_exec_id)
        self.started = False

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

    def _send_mq_dao_flush_complete(self, interceptor_instance_id, exec_bundle_id=None):
        msg = {
            "type": "flowcept_control",
            "info": "mq_flush_complete",
            "interceptor_instance_id": interceptor_instance_id,
            "exec_bundle_id": exec_bundle_id,
        }
        self.send_message(msg)

    def send_document_inserter_stop(self, exec_bundle_id=None):
        """Send the document."""
        # These control_messages are handled by the document inserter
        msg = {"type": "flowcept_control", "info": "stop_document_inserter", "exec_bundle_id": exec_bundle_id}
        self.send_message(msg)

    @abstractmethod
    def send_message(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
        """Send a message."""
        raise NotImplementedError()

    @abstractmethod
    def _send_message_timed(self, message: dict, channel=MQ_CHANNEL, serializer=msgpack.dumps):
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
    def unsubscribe(self):
        """Subscribe to the interception channel."""
        raise NotImplementedError()

    @abstractmethod
    def liveness_test(self) -> bool:
        """Checks if the MQ system is alive."""
        raise NotImplementedError()
