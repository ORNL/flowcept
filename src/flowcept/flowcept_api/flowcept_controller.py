"""Controller module."""

from typing import List, Union
from uuid import uuid4

from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import ClassProperty
from flowcept.configs import MQ_INSTANCES, INSTRUMENTATION_ENABLED, MONGO_ENABLED, SETTINGS_PATH
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


class Flowcept(object):
    """Flowcept Controller class."""

    _db = None
    current_workflow_id = None
    campaign_id = None

    @ClassProperty
    def db(cls):
        """Property to expose the DBAPI. This also assures the DBAPI init will be called once."""
        if cls._db is None:
            from flowcept.flowcept_api.db_api import DBAPI

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
        save_workflow=True,
        *args,
        **kwargs,
    ):
        """
        Initialize the Flowcept controller.

        This class manages interceptors and workflow tracking. If used for instrumentation,
        each workflow should have its own instance of this class.

        Parameters
        ----------
        interceptors : Union[BaseInterceptor, List[BaseInterceptor], str], optional
            A list of interceptors (or a single interceptor) to apply. Each entry can be:
            - A subclass of `BaseInterceptor`
            - A string for special cases (e.g., "instrumentation" or "dask")
            - If None, instrumentation is used by default.

            The order of interceptors matters—place the outer-most interceptor first,
            especially if `save_workflow` is enabled, since it will handle workflow saving.

        bundle_exec_id : Any, optional
            Identifier for grouping interceptors in a bundle, essential for the correct initialization and stop of
            interceptors. If not provided, a unique ID is assigned.

        campaign_id : str, optional
            A unique identifier for the campaign. If not provided, a new one is generated.

        workflow_id : str, optional
            A unique identifier for the workflow.

        workflow_name : str, optional
            A descriptive name for the workflow.

        workflow_args : str, optional
            Additional arguments related to the workflow.

        start_persistence : bool, default=True
            If True, enables message persistence in the configured databases.

        save_workflow : bool, default=True
            If True, a workflow object message is sent.

        Additional arguments (`*args`, `**kwargs`) are used for specific adapters.
            For example, when using the Dask interceptor, the `dask_client` argument
            should be provided in `kwargs` to enable saving the Dask workflow, which is recommended.
        """
        self.logger = FlowceptLogger()
        self.logger.debug(f"Using settings file: {SETTINGS_PATH}")
        self._enable_persistence = start_persistence
        self._db_inserters: List = []
        if bundle_exec_id is None:
            self._bundle_exec_id = id(self)
        else:
            self._bundle_exec_id = bundle_exec_id

        self.enabled = True
        self.is_started = False
        self.args = args
        self.kwargs = kwargs

        if interceptors:
            if not isinstance(interceptors, list):
                interceptors = [interceptors]

            self._interceptors: List[BaseInterceptor] = []
            # self._interceptors = interceptors

            for interceptor in interceptors:
                if isinstance(interceptor, str):
                    if interceptor == "instrumentation":
                        self._interceptors.append(InstrumentationInterceptor.get_instance())
                    elif interceptor == "dask":
                        from flowcept.flowceptor.adapters.dask.dask_interceptor import DaskWorkerInterceptor

                        # This happens when the interceptor.starter is at the data system (e.g., dask)
                        # because they don't have an explicit interceptor. They emit by themselves
                        self._interceptors.append(DaskWorkerInterceptor())
                    else:
                        self._interceptors.append(None)
                elif isinstance(interceptor, BaseInterceptor):
                    self._interceptors.append(interceptor)
        else:
            if not INSTRUMENTATION_ENABLED:
                self._interceptors = None
                self.enabled = False
            else:
                self._interceptors = [InstrumentationInterceptor.get_instance()]

        self._save_workflow = save_workflow
        self._workflow_saved = False
        self.current_workflow_id = workflow_id
        self.campaign_id = campaign_id or str(uuid4())
        self.workflow_name = workflow_name
        self.workflow_args = workflow_args

    def start(self):
        """Start it."""
        if self.is_started or not self.enabled:
            self.logger.warning("DB inserter may be already started or instrumentation is not set")
            return self

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

        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                if interceptor is None:
                    continue

                Flowcept.campaign_id = self.campaign_id

                if interceptor.kind not in BaseInterceptor.KINDS_TO_NOT_EXPLICITLY_CONTROL:
                    self.logger.debug(f"Flowceptor {interceptor.kind} starting...")
                    interceptor.start(bundle_exec_id=self._bundle_exec_id)
                    self.logger.debug(f"Flowceptor {interceptor.kind} started.")

                if interceptor.kind == "instrumentation":
                    interceptor._mq_dao.set_campaign_id(Flowcept.campaign_id)
                    if self._save_workflow and not self._workflow_saved:
                        self.save_workflow(interceptor)
                        self._workflow_saved = True
                elif interceptor.kind == "dask":
                    if self._save_workflow and not self._workflow_saved:
                        dask_client = self.kwargs.get("dask_client", None)
                        if not dask_client:
                            raise Exception("You must give the argument `dask_client` so we can save the workflow.")
                        from flowcept.flowceptor.adapters.dask.dask_plugins import save_dask_workflow

                        wf_id = save_dask_workflow(
                            dask_client,
                            used=self.workflow_args,
                            workflow_id=self.current_workflow_id,
                            workflow_name=self.workflow_name,
                            campaign_id=Flowcept.campaign_id,
                        )
                        Flowcept.current_workflow_id = self.current_workflow_id or wf_id

        else:
            Flowcept.current_workflow_id = None
        self.is_started = True
        self.logger.debug("Flowcept started successfully.")
        return self

    def save_workflow(self, interceptor):
        """
        Save the current workflow and send its metadata using the provided interceptor.

        This method assigns a unique workflow ID if one does not already exist, creates a
        `WorkflowObject`, and populates it with relevant metadata such as campaign ID,
        workflow name, and arguments. The interceptor is then used to send the workflow data.

        Parameters
        ----------
        interceptor : object
            An object responsible for sending the workflow message, expected to have a
            `send_workflow_message` method.

        Returns
        -------
        None
        """
        Flowcept.current_workflow_id = self.current_workflow_id or str(uuid4())
        wf_obj = WorkflowObject()
        wf_obj.workflow_id = Flowcept.current_workflow_id
        wf_obj.campaign_id = Flowcept.campaign_id
        if self.workflow_name:
            wf_obj.name = self.workflow_name
        if self.workflow_args:
            wf_obj.used = self.workflow_args
        interceptor.send_workflow_message(wf_obj)

    def _init_persistence(self, mq_host=None, mq_port=None):
        from flowcept.flowceptor.consumers.document_inserter import DocumentInserter

        self._db_inserters.append(
            DocumentInserter(
                check_safe_stops=True,
                bundle_exec_id=self._bundle_exec_id,
            ).start()
        )

    def stop(self):
        """Stop it."""
        if not self.is_started or not self.enabled:
            self.logger.warning("Flowcept is already stopped or may never have been started!")
            return

        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                if interceptor is None:
                    continue

                if interceptor.kind not in BaseInterceptor.KINDS_TO_NOT_EXPLICITLY_CONTROL:
                    self.logger.debug(f"Flowceptor {interceptor.kind} stopping...")
                    interceptor.stop()
                    self.logger.debug(f"Flowceptor {interceptor.kind} stopped.")

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
        """
        Checks the liveness of the MQ (Message Queue) and, if enabled, the MongoDB service.

        Returns
        -------
        bool
            True if all services (MQ and optionally MongoDB) are alive, False otherwise.

        Notes
        -----
        - The method tests the liveness of the MQ service using `MQDao`.
        - If `MONGO_ENABLED` is True, it also checks the liveness of the MongoDB service
          using `MongoDBDAO`.
        - Logs errors if any service is not ready, and logs success when both services are
        operational.

        Examples
        --------
        >>> is_alive = services_alive()
        >>> if is_alive:
        ...     print("All services are running.")
        ... else:
        ...     print("One or more services are not ready.")
        """
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

    @staticmethod
    def start_consumption_services(bundle_exec_id: str = None, check_safe_stops: bool = False, consumers: List = None):
        """
        Starts the document consumption services for processing.

        Parameters
        ----------
        bundle_exec_id : str, optional
            The execution ID of the bundle being processed. Defaults to None.
        check_safe_stops : bool, optional
            Whether to enable safe stop checks for the service. Defaults to False.
        consumers : List, optional
            A list of consumer types to be started. Currently, only one type of consumer
            is supported. Defaults to None.

        Raises
        ------
        NotImplementedError
            If multiple consumer types are provided in the `consumers` list.

        Notes
        -----
        - The method initializes the `DocumentInserter` service, which processes documents
          based on the provided parameters.
        - The `threaded` parameter for `DocumentInserter.start` is set to `False`.

        Examples
        --------
        >>> start_consumption_services(bundle_exec_id="12345", check_safe_stops=True)
        """
        if consumers is not None:
            raise NotImplementedError("We currently only have one type of consumer.")
        from flowcept.flowceptor.consumers.document_inserter import DocumentInserter

        logger = FlowceptLogger()
        doc_inserter = DocumentInserter(check_safe_stops=check_safe_stops, bundle_exec_id=bundle_exec_id)
        logger.debug("Starting doc inserter service.")
        doc_inserter.start(threaded=False)
