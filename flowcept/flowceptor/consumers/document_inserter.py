import json
from time import time, sleep
from threading import Thread, Event
from typing import Dict
from datetime import datetime
from flowcept.configs import (
    MONGO_INSERTION_BUFFER_TIME,
    MONGO_INSERTION_BUFFER_SIZE,
    DEBUG_MODE,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao import MQDao
from flowcept.commons.daos.document_db_dao import DocumentDBDao


class DocumentInserter:
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

    def handle_task_message(self, message: Dict):
        if "utc_timestamp" in message:
            dt = datetime.fromtimestamp(message["utc_timestamp"])
            message["timestamp"] = dt.utcnow()

        if DEBUG_MODE:
            message["debug"] = True

        self._buffer.append(message)
        self.logger.debug("An intercepted message was received.")
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
            _dict_obj = json.loads(message["data"])
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
        self._main_thread.join()
        self.logger.info("Document Inserter is stopped.")
