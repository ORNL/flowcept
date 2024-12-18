"""Controller module."""

from typing import List, Union
from time import sleep
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.configs import MQ_INSTANCES, INSTRUMENTATION_ENABLED, MONGO_ENABLED
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor


class Flowcept(object):
    """Flowcept Controller class."""

    _db: DBAPI = None
    current_workflow_id = None
    campaign_id = None

    @classmethod
    @property
    def db(cls) -> DBAPI:
        """Property to expose the DBAPI. This also assures the DBAPI init will be called once."""
        if cls._db is None:
            cls._db = DBAPI()
        return cls._db

    def __init__(
        self,
        interceptors: Union[BaseInterceptor, List[BaseInterceptor], str] = None,
        bundle_exec_id=None,
        campaign_id: str = None,
        workflow_id: str = None,
        workflow_name: str = None,
        workflow_args: str = None,
        start_persistence=True,
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

        start_persistence - Whether you want to persist the messages in one of the DBs defined in
         the `databases` settings.
        """
        self.logger = FlowceptLogger()
        self._enable_persistence = start_persistence
        self._db_inserters: List = []
        if bundle_exec_id is None:
            self._bundle_exec_id = id(self)
        else:
            self._bundle_exec_id = bundle_exec_id
        self.enabled = True
        self.is_started = False
        if isinstance(interceptors, str):
            # This happens when the interceptor.starter is at the data system (e.g., dask)
            # because they don't have an explicit interceptor. They emit by themselves
            self._interceptors = None
        else:
            if interceptors is None:
                if not INSTRUMENTATION_ENABLED:
                    self.enabled = False
                    return
                interceptors = [InstrumentationInterceptor.get_instance()]
            elif not isinstance(interceptors, list):
                interceptors = [interceptors]
            self._interceptors: List[BaseInterceptor] = interceptors

        self.current_workflow_id = workflow_id
        self.campaign_id = campaign_id
        self.workflow_name = workflow_name
        self.workflow_args = workflow_args

    def start(self):
        """Start it."""
        if self.is_started or not self.enabled:
            self.logger.warning("DB inserter may be already started or instrumentation is not set")
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

                if interceptor.kind == "instrumentation":
                    wf_obj = WorkflowObject()
                    wf_obj.workflow_id = self.current_workflow_id or str(uuid4())
                    wf_obj.campaign_id = self.campaign_id or str(uuid4())

                    Flowcept.current_workflow_id = wf_obj.workflow_id
                    Flowcept.campaign_id = wf_obj.campaign_id

                    if self.workflow_name:
                        wf_obj.name = self.workflow_name
                    if self.workflow_args:
                        wf_obj.used = self.workflow_args
                    interceptor.send_workflow_message(wf_obj)
                else:
                    Flowcept.current_workflow_id = None

        if self._enable_persistence:
            self.logger.debug("Flowcept persistence starting...")
            if MQ_INSTANCES is not None and len(MQ_INSTANCES):
                for mq_host_port in MQ_INSTANCES:
                    split = mq_host_port.split(":")
                    mq_host = split[0]
                    mq_port = int(split[1])
                    self._init_persistence(mq_host, mq_port)
            else:
                self._init_persistence()

        self.logger.debug("Ok, we're consuming messages to persist!")
        self.is_started = True
        return self

    def _init_persistence(self, mq_host=None, mq_port=None):
        from flowcept.flowceptor.consumers.document_inserter import DocumentInserter

        self._db_inserters.append(
            DocumentInserter(
                check_safe_stops=True,
                bundle_exec_id=self._bundle_exec_id,
                mq_host=mq_host,
                mq_port=mq_port,
            ).start()
        )

    def stop(self):
        """Stop it."""
        if not self.is_started or not self.enabled:
            self.logger.warning("Persistence is already stopped!")
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
        if len(self._db_inserters):
            self.logger.info("Stopping DB Inserters...")
            for db_inserter in self._db_inserters:
                db_inserter.stop(bundle_exec_id=self._bundle_exec_id)
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
    def services_alive() -> bool:
        """Get alive services."""
        logger = FlowceptLogger()
        if not MQDao.build().liveness_test():
            logger.error("MQ Not Ready!")
            return False
        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

            if not MongoDBDAO(create_indices=False).liveness_test():
                logger.error("DocDB Not Ready!")
                return False
        logger.info("MQ and DocDB are alive!")
        return True
