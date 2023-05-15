import json
from time import time, sleep
from threading import Thread, Event
from typing import Dict
from datetime import datetime

from flowcept.commons.utils import GenericJSONDecoder
from flowcept.configs import (
    MONGO_INSERTION_BUFFER_TIME,
    MONGO_INSERTION_BUFFER_SIZE,
    DEBUG_MODE, JSON_SERIALIZER,
    MONGO_REMOVE_EMPTY_FIELDS
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

    def _flush(self):
        if len(self._buffer):
            self._doc_dao.insert_and_update_many("task_id", self._buffer)
            self._buffer = list()
            self.logger.debug("Flushed!")

    def handle_task_message(self, message: Dict):
        if "utc_timestamp" in message:
            dt = datetime.fromtimestamp(message["utc_timestamp"])
            message["timestamp"] = dt.utcnow()

        if DEBUG_MODE:
            message["debug"] = True

        self.logger.debug("An intercepted msg was received in DocInserter:")
        if MONGO_REMOVE_EMPTY_FIELDS:
            remove_empty_fields_from_dict(message)
        self.logger.debug("\t"+str(message))
        self._buffer.append(message)

        if len(self._buffer) >= MONGO_INSERTION_BUFFER_SIZE:
            self.logger.debug("Buffer exceeded, flushing...")
            self._flush()

    def time_based_flushing(self, event: Event):
        while not event.is_set():
            if len(self._buffer):
                now = time()
                timediff = now - self._previous_time
                if timediff >= MONGO_INSERTION_BUFFER_TIME:
                    self.logger.debug("Time to flush!")
                    self._previous_time = now
                    self._flush()
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
                    break
            else:
                self.handle_task_message(_dict_obj)

        time_thread.join()

    def stop(self):
        self._mq_dao.stop_document_inserter()
        self._mq_dao.stop()
        self._main_thread.join()
        self.logger.info("Document Inserter is stopped.")
