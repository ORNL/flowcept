"""Controller module."""

from typing import List, Union
from time import sleep

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)

import flowcept.instrumentation.decorators
from flowcept.commons import logger
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.configs import (
    MQ_INSTANCES,
    INSTRUMENTATION_ENABLED,
)
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.flowceptor.consumers.document_inserter import DocumentInserter
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor


class Flowcept(object):
    """Flowcept class."""

    db = DBAPI()
    current_workflow_id = None

    def __init__(
        self,
        interceptors: Union[BaseInterceptor, List[BaseInterceptor], str] = None,
        bundle_exec_id=None,
        start_doc_inserter=True,
        workflow_id: str = None,
        workflow_name: str = None,
        workflow_args: str = None,
    ):
        """Flowcept controller.

        This class controls the interceptors, including instrumentation.
        If using for instrumentation, we assume one instance of this class
        per workflow is being utilized.

        Parameters
        ----------
        interceptors - list of Flowcept interceptors. If none, instrumentation
        will be used. If a string is passed, no interceptor will be
        started. # TODO: improve clarity for the documentation.

        bundle_exec_id - A way to group interceptors.

        start_doc_inserter - Whether you want to start consuming MQ messages to inject in the DB.
        """
        self.logger = FlowceptLogger()

        self._document_inserters: List[DocumentInserter] = []
        self._start_doc_inserter = start_doc_inserter
        if bundle_exec_id is None:
            self._bundle_exec_id = id(self)
        else:
            self._bundle_exec_id = bundle_exec_id
        self.enabled = True
        self.is_started = False
        if isinstance(interceptors, str):
            self._interceptors = None
        else:
            if interceptors is None:
                if not INSTRUMENTATION_ENABLED:
                    self.enabled = False
                    return
                interceptors = [flowcept.instrumentation.decorators.instrumentation_interceptor]
            elif not isinstance(interceptors, list):
                interceptors = [interceptors]
            self._interceptors: List[BaseInterceptor] = interceptors

        self.current_workflow_id = workflow_id
        self.workflow_name = workflow_name
        self.workflow_args = workflow_args

    def start(self):
        """Start it."""
        if self.is_started or not self.enabled:
            self.logger.warning("Consumer may be already started or instrumentation is not set")
            return self

        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                # TODO: :base-interceptor-refactor: revise
                if interceptor.settings is None:
                    key = id(interceptor)
                else:
                    key = interceptor.settings.key
                self.logger.debug(f"Flowceptor {key} starting...")
                interceptor.start(bundle_exec_id=self._bundle_exec_id)
                self.logger.debug(f"...Flowceptor {key} started ok!")

                if (
                    self.current_workflow_id or self.workflow_args or self.workflow_name
                ) and interceptor.kind == "instrumentation":
                    wf_obj = WorkflowObject(
                        self.current_workflow_id,
                        self.workflow_name,
                        used=self.workflow_args,
                    )
                    interceptor.send_workflow_message(wf_obj)
                    Flowcept.current_workflow_id = wf_obj.workflow_id
                else:
                    Flowcept.current_workflow_id = None

        if self._start_doc_inserter:
            self.logger.debug("Flowcept Consumer starting...")

            if MQ_INSTANCES is not None and len(MQ_INSTANCES):
                for mq_host_port in MQ_INSTANCES:
                    split = mq_host_port.split(":")
                    mq_host = split[0]
                    mq_port = int(split[1])
                    self._document_inserters.append(
                        DocumentInserter(
                            check_safe_stops=True,
                            mq_host=mq_host,
                            mq_port=mq_port,
                            bundle_exec_id=self._bundle_exec_id,
                        ).start()
                    )
            else:
                self._document_inserters.append(
                    DocumentInserter(
                        check_safe_stops=True,
                        bundle_exec_id=self._bundle_exec_id,
                    ).start()
                )
        self.logger.debug("Ok, we're consuming messages!")
        self.is_started = True
        return self

    def stop(self):
        """Stop it."""
        if not self.is_started or not self.enabled:
            self.logger.warning("Consumer is already stopped!")
            return
        sleep_time = 1
        self.logger.info(
            f"Received the stop signal. We're going to wait {sleep_time} secs."
            f" before gracefully stopping..."
        )
        sleep(sleep_time)
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                # TODO: :base-interceptor-refactor: revise
                if interceptor.settings is None:
                    key = id(interceptor)
                else:
                    key = interceptor.settings.key
                self.logger.info(f"Flowceptor {key} stopping...")
                interceptor.stop()
        if self._start_doc_inserter:
            self.logger.info("Stopping Doc Inserters...")
            for doc_inserter in self._document_inserters:
                doc_inserter.stop(bundle_exec_id=self._bundle_exec_id)
        self.is_started = False
        self.logger.debug("All stopped!")

    def __enter__(self):
        """Run the start function."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Run the stop function."""
        self.stop()

    @staticmethod
    def start_instrumentation_interceptor():
        """Start it."""
        flowcept.instrumentation.decorators.instrumentation_interceptor.start(None)

    @staticmethod
    def services_alive() -> bool:
        """Get alive services."""
        if not MQDao.build().liveness_test():
            logger.error("MQ Not Ready!")
            return False
        if not DocumentDBDao().liveness_test():
            logger.error("DocDB Not Ready!")
            return False
        logger.info("MQ and DocDB are alive!")
        return True
