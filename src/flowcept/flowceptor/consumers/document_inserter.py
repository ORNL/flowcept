"""Document module."""

from datetime import datetime
from time import time, sleep
from threading import Thread, Event, Lock
from typing import Dict
from uuid import uuid4

import pytz

import flowcept.commons
from flowcept.commons.daos.autoflush_buffer import AutoflushBuffer
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.utils import GenericJSONDecoder
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.configs import (
    MONGO_INSERTION_BUFFER_TIME,
    MONGO_MAX_BUFFER_SIZE,
    MONGO_MIN_BUFFER_SIZE,
    MONGO_ADAPTIVE_BUFFER_SIZE,
    JSON_SERIALIZER,
    MONGO_REMOVE_EMPTY_FIELDS,
    ENRICH_MESSAGES,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.flowceptor.consumers.consumer_utils import (
    remove_empty_fields_from_dict,
)


class DocumentInserter:
    """Document class."""

    DECODER = GenericJSONDecoder if JSON_SERIALIZER == "complex" else None

    # TODO: :code-reorg: Should this be in utils?
    @staticmethod
    def remove_empty_fields(d):
        """Remove empty fields from a dictionary recursively."""
        for key, value in list(d.items()):
            if isinstance(value, dict):
                DocumentInserter.remove_empty_fields(value)
                if not value:
                    del d[key]
            elif value in (None, ""):
                del d[key]

    def __init__(
        self,
        check_safe_stops=True,
        mq_host=None,
        mq_port=None,
        bundle_exec_id=None,
    ):
        self._task_dicts_buffer = list()
        self._mq_dao = MQDao.build(mq_host, mq_port)
        self._doc_dao = DocumentDBDao()
        self._previous_time = time()
        self.logger = FlowceptLogger()
        self._main_thread: Thread = None
        self._curr_max_buffer_size = MONGO_MAX_BUFFER_SIZE
        self._lock = Lock()
        self._bundle_exec_id = bundle_exec_id
        self.check_safe_stops = check_safe_stops
        self.buffer: AutoflushBuffer = AutoflushBuffer(
            max_size=self._curr_max_buffer_size,
            flush_interval=MONGO_INSERTION_BUFFER_TIME,
            flush_function=DocumentInserter.flush_function,
            doc_dao=self._doc_dao,
        )

    def _set_buffer_size(self):
        if not MONGO_ADAPTIVE_BUFFER_SIZE:
            return
        else:
            # Adaptive buffer size to increase/decrease depending on the flow
            # of messages (#messages/unit of time)
            if len(self._task_dicts_buffer) >= MONGO_MAX_BUFFER_SIZE:
                self._curr_max_buffer_size = MONGO_MAX_BUFFER_SIZE
            elif len(self._task_dicts_buffer) < self._curr_max_buffer_size:
                # decrease buffer size by 10%, lower-bounded by 10
                self._curr_max_buffer_size = max(
                    MONGO_MIN_BUFFER_SIZE,
                    int(self._curr_max_buffer_size * 0.9),
                )
            else:
                # increase buffer size by 10%,
                # upper-bounded by MONGO_INSERTION_BUFFER_SIZE
                self._curr_max_buffer_size = max(
                    MONGO_MIN_BUFFER_SIZE,
                    min(
                        MONGO_MAX_BUFFER_SIZE,
                        int(self._curr_max_buffer_size * 1.1),
                    ),
                )

    @staticmethod
    def flush_function(buffer, doc_dao, logger=flowcept.commons.logger):
        """Flush it."""
        logger.info(
            f"Current Doc buffer size: {len(buffer)}, " f"Gonna flush {len(buffer)} msgs to DocDB!"
        )
        inserted = doc_dao.insert_and_update_many(TaskObject.task_id_field(), buffer)
        if not inserted:
            logger.warning(f"Could not insert the buffer correctly. " f"Buffer content={buffer}")
        else:
            logger.info(f"Flushed {len(buffer)} msgs to DocDB!")

    def _handle_task_message(self, message: Dict):
        # if DEBUG_MODE:
        #     message["debug"] = True
        if "task_id" not in message:
            message["task_id"] = str(uuid4())

        if "workflow_id" not in message and len(message.get("used", {})):
            wf_id = message.get("used").get("workflow_id", None)
            if wf_id:
                message["workflow_id"] = wf_id

        has_time_fields = False
        for time_field in TaskObject.get_time_field_names():
            if time_field in message:
                has_time_fields = True
                message[time_field] = datetime.fromtimestamp(message[time_field], pytz.utc)

        if not has_time_fields:
            message["registered_at"] = datetime.fromtimestamp(time(), pytz.utc)

        if ENRICH_MESSAGES:
            TaskObject.enrich_task_dict(message)

        message.pop("type")

        self.logger.debug(
            f"Received following msg in DocInserter:" f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
        )
        if MONGO_REMOVE_EMPTY_FIELDS:
            remove_empty_fields_from_dict(message)

        self.buffer.append(message)
        # with self._lock:
        #     self._task_dicts_buffer.append(message)
        #     if len(self._task_dicts_buffer) >= self._curr_max_buffer_size:
        #         self.logger.debug("Docs buffer exceeded, flushing...")
        #         self._flush()

    def _handle_workflow_message(self, message: Dict):
        message.pop("type")
        self.logger.debug(
            f"Received following msg in DocInserter:" f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
        )
        if MONGO_REMOVE_EMPTY_FIELDS:
            remove_empty_fields_from_dict(message)
        wf_obj = WorkflowObject.from_dict(message)
        inserted = self._doc_dao.workflow_insert_or_update(wf_obj)
        return inserted

    def _handle_control_message(self, message):
        self.logger.info(
            f"I'm doc inserter {id(self)}. I received this control msg received: {message}"
        )
        if message["info"] == "mq_dao_thread_stopped":
            exec_bundle_id = message.get("exec_bundle_id", None)
            interceptor_instance_id = message.get("interceptor_instance_id")
            self.logger.info(
                f"DocInserter id {id(self)}. Received mq_dao_thread_stopped message "
                f"in DocInserter from the interceptor "
                f"{'' if exec_bundle_id is None else exec_bundle_id}_{interceptor_instance_id}!"
            )
            self.logger.info(
                f"Begin register_time_based_thread_end "
                f"{'' if exec_bundle_id is None else exec_bundle_id}_{interceptor_instance_id}!"
            )
            self._mq_dao.register_time_based_thread_end(interceptor_instance_id, exec_bundle_id)
            self.logger.info(
                f"Done register_time_based_thread_end "
                f"{'' if exec_bundle_id is None else exec_bundle_id}_{interceptor_instance_id}!"
            )
            return "continue"
        elif message["info"] == "stop_document_inserter":
            self.logger.info("Document Inserter is stopping...")
            return "stop"

    def start(self) -> "DocumentInserter":
        """Start it."""
        self._main_thread = Thread(target=self._start)
        self._main_thread.start()
        return self

    def _start(self):
        stop_event = Event()
        while True:
            try:
                self._mq_dao.message_listener(self._message_handler)
                stop_event.set()
                self.buffer.stop()
                break
            except Exception as e:
                self.logger.exception(e)
                sleep(2)
            self.logger.debug("Still in the doc insert. message listen loop")
        self.logger.info("Ok, we broke the doc inserter message listen loop!")

    def _message_handler(self, msg_obj: dict):
        msg_type = msg_obj.get("type")
        if msg_type == "flowcept_control":
            r = self._handle_control_message(msg_obj)
            if r == "stop":
                return False
            return True
        elif msg_type == "task":
            self._handle_task_message(msg_obj)
            return True
        elif msg_type == "workflow":
            self._handle_workflow_message(msg_obj)
            return True
        elif msg_type is None:
            self.logger.warning(f"Message without type???\n {msg_obj}")
            return True
            # raise Exception("Please inform the message type.")
        else:
            self.logger.error("Unexpected message type")
            return True

    def stop(self, bundle_exec_id=None):
        """Stop it."""
        if self.check_safe_stops:
            max_trials = 60
            trial = 0
            while not self._mq_dao.all_time_based_threads_ended(bundle_exec_id):
                trial += 1
                sleep_time = 3
                self.logger.info(
                    f"Doc Inserter {id(self)}: It's still not safe to stop DocInserter. "
                    f"Checking again in {sleep_time} secs. Trial={trial}."
                )
                sleep(sleep_time)
                if trial >= max_trials:
                    if len(self._task_dicts_buffer) == 0:  # and len(self._mq_dao._buffer) == 0:
                        msg = f"DocInserter {id(self)} gave up waiting for signal. "
                        self.logger.critical(msg + "Safe to stop now.")
                        break
        self.logger.info("Sending message to stop document inserter.")
        self._mq_dao.send_document_inserter_stop()
        self.logger.info(f"Doc Inserter {id(self)} Sent message to stop itself.")
        self._main_thread.join()
        self.logger.info("Document Inserter is stopped.")
