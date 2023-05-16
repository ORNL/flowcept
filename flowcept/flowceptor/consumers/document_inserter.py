import json
from time import time, sleep
from threading import Thread, Event, Lock
from typing import Dict
from datetime import datetime

from flowcept.commons.utils import GenericJSONDecoder
from flowcept.commons.flowcept_data_classes import TaskMessage
from flowcept.configs import (
    MONGO_INSERTION_BUFFER_TIME,
    MONGO_INSERTION_BUFFER_SIZE,
    DEBUG_MODE, JSON_SERIALIZER,
    MONGO_REMOVE_EMPTY_FIELDS,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao import MQDao
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.flowceptor.consumers.consumer_utils import \
    remove_empty_fields_from_dict


class DocumentInserter:

    DECODER = GenericJSONDecoder if JSON_SERIALIZER == "complex" else None
    
    @staticmethod
    def remove_empty_fields(d):
        """Remove empty fields from a dictionary recursively."""
        for key, value in list(d.items()):
            if isinstance(value, dict):
                DocumentInserter.remove_empty_fields(value)
                if not value:
                    del d[key]
            elif value in (None, ''):
                del d[key]
    
    def __init__(self):
        self._buffer = list()
        self._mq_dao = MQDao()
        self._doc_dao = DocumentDBDao()
        self._previous_time = time()
        self.logger = FlowceptLogger().get_logger()
        self._main_thread: Thread = None
        self._curr_max_buffer_size = MONGO_INSERTION_BUFFER_SIZE
        self._lock = Lock()

    def _flush(self):
        if len(self._buffer):
            # Adaptive buffer size to increase/decrease depending on the flow
            # of messages (#messages/unit of time)
            if len(self._buffer) >= MONGO_INSERTION_BUFFER_SIZE:
                self._curr_max_buffer_size = MONGO_INSERTION_BUFFER_SIZE
            elif len(self._buffer) <= self._curr_max_buffer_size:
                # decrease buffer size by 10%, lower-bounded by 10
                self._curr_max_buffer_size = max(10,
                                                 int(len(self._buffer) * 0.9))
            else:
                # increase buffer size by 10%, upper-bounded by MONGO_INSERTION_BUFFER_SIZE
                self._curr_max_buffer_size = min(MONGO_INSERTION_BUFFER_SIZE,
                                                 int(len(self._buffer) * 1.1))

            with self._lock:
                self.logger.debug(
                    f"Current buffer size: {len(self._buffer)}, "
                    f"Gonna flush {len(self._buffer)} msgs to DocDB!")
                inserted = self._doc_dao.insert_and_update_many(TaskMessage.get_index_field(), self._buffer)
                if not inserted:
                    self.logger.error(f"Could not insert the buffer correctly. Buffer content={self._buffer}")
                else:
                    self.logger.debug(
                        f"Flushed {len(self._buffer)} msgs to DocDB!")
                self._buffer = list()

    def handle_task_message(self, message: Dict):
        if "utc_timestamp" in message:
            dt = datetime.fromtimestamp(message["utc_timestamp"])
            message["timestamp"] = dt.utcnow()

        if DEBUG_MODE:
            message["debug"] = True

        self.logger.debug(
            f"Received following msg in DocInserter:"
            f"\n\t[BEGINMSG]{message}\n\t[ENDMSG]"
        )
        if MONGO_REMOVE_EMPTY_FIELDS:
            remove_empty_fields_from_dict(message)
        self._buffer.append(message)

        if len(self._buffer) >= self._curr_max_buffer_size:
            self.logger.debug("Docs buffer exceeded, flushing...")
            self._flush()

    def time_based_flushing(self, event: Event):
        while not event.is_set():
            if len(self._buffer):
                now = time()
                timediff = now - self._previous_time
                if timediff >= MONGO_INSERTION_BUFFER_TIME:
                    self.logger.debug("Time to flush to doc db!")
                    self._previous_time = now
                    self._flush()
            self.logger.debug(
                f"Time-based DocDB inserter going to wait for {MONGO_INSERTION_BUFFER_TIME} s.")
            sleep(MONGO_INSERTION_BUFFER_TIME)

    def start(self):
        self._main_thread = Thread(target=self._start)
        self._main_thread.start()
        return self

    def _start(self):
        stop_event = Event()
        time_thread = Thread(
            target=self.time_based_flushing, args=(stop_event,)
        )
        time_thread.start()
        pubsub = self._mq_dao.subscribe()

        should_continue = True
        while should_continue:
            try:
                for message in pubsub.listen():
                    if message["type"] in MQDao.MESSAGE_TYPES_IGNORE:
                        continue
                    _dict_obj = json.loads(message["data"], cls=DocumentInserter.DECODER)
                    if (
                        "type" in _dict_obj
                        and _dict_obj["type"] == "flowcept_control"
                    ):
                        if _dict_obj["info"] == "stop_document_inserter":
                            self.logger.info("Document Inserter is stopping...")
                            stop_event.set()
                            self._flush()
                            should_continue = False
                            break
                    else:
                        self.handle_task_message(_dict_obj)
            except Exception as e:
                self.logger.exception(e)
                sleep(2)

        time_thread.join()

    def stop(self):
        self._mq_dao.stop_document_inserter()
        self._mq_dao.stop()
        self._main_thread.join()
        self._flush()
        self.logger.info("Document Inserter is stopped.")
