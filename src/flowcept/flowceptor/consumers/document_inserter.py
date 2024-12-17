"""Document Inserter module."""

from time import time, sleep
from threading import Thread, Event, Lock
from typing import Dict
from uuid import uuid4

from flowcept.commons.autoflush_buffer import AutoflushBuffer

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.utils import GenericJSONDecoder
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.configs import (
    INSERTION_BUFFER_TIME,
    MAX_BUFFER_SIZE,
    MIN_BUFFER_SIZE,
    ADAPTIVE_BUFFER_SIZE,
    REMOVE_EMPTY_FIELDS,
    JSON_SERIALIZER,
    ENRICH_MESSAGES,
    MONGO_ENABLED,
    LMDB_ENABLED,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao

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
        self._doc_daos = []
        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

            self._doc_daos.append(MongoDBDAO())
        if LMDB_ENABLED:
            from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO

            self._doc_daos.append(LMDBDAO())
        self._previous_time = time()
        self.logger = FlowceptLogger()
        self._main_thread: Thread = None
        self._curr_max_buffer_size = MAX_BUFFER_SIZE
        self._lock = Lock()
        self._bundle_exec_id = bundle_exec_id
        self.check_safe_stops = check_safe_stops
        self.buffer: AutoflushBuffer = AutoflushBuffer(
            max_size=self._curr_max_buffer_size,
            flush_interval=INSERTION_BUFFER_TIME,
            logger=self.logger,
            flush_function=DocumentInserter.flush_function,
            flush_function_kwargs={"logger": self.logger, "doc_daos": self._doc_daos},
        )

    def _set_buffer_size(self):
        if not ADAPTIVE_BUFFER_SIZE:
            return
        else:
            # Adaptive buffer size to increase/decrease depending on the flow
            # of messages (#messages/unit of time)
            if len(self._task_dicts_buffer) >= MAX_BUFFER_SIZE:
                self._curr_max_buffer_size = MAX_BUFFER_SIZE
            elif len(self._task_dicts_buffer) < self._curr_max_buffer_size:
                # decrease buffer size by 10%, lower-bounded by 10
                self._curr_max_buffer_size = max(
                    MIN_BUFFER_SIZE,
                    int(self._curr_max_buffer_size * 0.9),
                )
            else:
                # increase buffer size by 10%,
                # upper-bounded by MONGO_INSERTION_BUFFER_SIZE
                self._curr_max_buffer_size = max(
                    MIN_BUFFER_SIZE,
                    min(
                        MAX_BUFFER_SIZE,
                        int(self._curr_max_buffer_size * 1.1),
                    ),
                )

    @staticmethod
    def flush_function(buffer, doc_daos, logger):
        """Flush it."""
        logger.info(
            f"Current Doc buffer size: {len(buffer)}, " f"Gonna flush {len(buffer)} msgs to DocDBs!"
        )
        for dao in doc_daos:
            dao.insert_and_update_many_tasks(buffer, TaskObject.task_id_field())
            logger.debug(
                f"DocDao={id(dao)},DocDaoClass={dao.__class__.__name__};"
                f" Flushed {len(buffer)} msgs to this DocDB!"
            )  # TODO: add name

    def _handle_task_message(self, message: Dict):
        if "task_id" not in message:
            message["task_id"] = str(uuid4())

        if "workflow_id" not in message and len(message.get("used", {})):
            wf_id = message.get("used").get("workflow_id", None)
            if wf_id:
                message["workflow_id"] = wf_id

        if ENRICH_MESSAGES:
            TaskObject.enrich_task_dict(message)

        message.pop("type")

        self.logger.debug(
            f"Received following Task msg in DocInserter:" f"\n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
        )
        if REMOVE_EMPTY_FIELDS:
            remove_empty_fields_from_dict(message)

        self.buffer.append(message)

    def _handle_workflow_message(self, message: Dict):
        message.pop("type")
        self.logger.debug(
            f"Received following Workflow msg in DocInserter: \n\t[BEGIN_MSG]{message}\n[END_MSG]\t"
        )
        if REMOVE_EMPTY_FIELDS:
            remove_empty_fields_from_dict(message)
        wf_obj = WorkflowObject.from_dict(message)
        for dao in self._doc_daos:
            dao.insert_or_update_workflow(wf_obj)

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
            self.logger.error(f"Message without type??? --> {msg_obj}")
            return True
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
        for dao in self._doc_daos:
            self.logger.info(f"Closing document_inserter {dao.__class__.__name__} connection.")
            dao.close()
        self.logger.info("Document Inserter is stopped.")
