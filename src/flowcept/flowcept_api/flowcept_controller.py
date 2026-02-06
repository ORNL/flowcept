"""Controller module."""

import os
from pathlib import Path
from typing import List, Dict, Any

import flowcept
from flowcept.commons.autoflush_buffer import AutoflushBuffer
from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import (
    ClassProperty,
    buffer_to_disk,
    resolve_dump_buffer_path,
    generate_pseudo_id,
)
from flowcept.configs import (
    MQ_INSTANCES,
    INSTRUMENTATION_ENABLED,
    MONGO_ENABLED,
    SETTINGS_PATH,
    LMDB_ENABLED,
    KVDB_ENABLED,
    MQ_ENABLED,
    DUMP_BUFFER_PATH,
    APPEND_WORKFLOW_ID_TO_PATH,
    APPEND_ID_TO_PATH,
)
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor


class Flowcept(object):
    """Main Flowcept controller class."""

    _db = None
    # TODO: rename current_workflow_id to workflow_id. This will be a major refactor
    current_workflow_id = None
    campaign_id = None
    buffer = None

    @ClassProperty
    def db(cls):
        """Property to expose the DBAPI. This also assures the DBAPI init will be called once."""
        if cls._db is None:
            from flowcept.flowcept_api.db_api import DBAPI

            cls._db = DBAPI()
        return cls._db

    def __init__(
        self,
        interceptors: List[str] = None,
        bundle_exec_id: str = None,
        campaign_id: str = None,
        workflow_id: str = None,
        workflow_name: str = None,
        workflow_args: Dict = None,
        start_persistence=True,
        check_safe_stops=True,  # TODO add to docstring
        save_workflow=True,
        delete_buffer_file=None,
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
            A list of interceptor kinds (or a single interceptor kind) to apply.
            Examples: "instrumentation", "dask", "mlflow", ...
            The order of interceptors matters — place the outer-most interceptor first,

        bundle_exec_id : str, optional
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

        delete_buffer_file : bool or None, optional
            If True, deletes any existing dump buffer file on startup.
            If None, uses project.dump_buffer.delete_previous_file from settings.yaml.

        Additional arguments (`*args`, `**kwargs`) are used for specific adapters.
            For example, when using the Dask interceptor, the `dask_client` argument
            should be provided in `kwargs` to enable saving the Dask workflow, which is recommended.
        """
        self.logger = FlowceptLogger()
        self.logger.debug(f"Using settings file: {SETTINGS_PATH}")
        self._enable_persistence = start_persistence
        self._db_inserters: List = []
        self.buffer = None
        self._check_safe_stops = check_safe_stops
        if bundle_exec_id is None:
            self.bundle_exec_id = generate_pseudo_id()
        else:
            self.bundle_exec_id = str(bundle_exec_id)

        self.enabled = True
        self.is_started = False
        self.args = args
        self.kwargs = kwargs

        if interceptors:
            self._interceptors = interceptors
            if not isinstance(self._interceptors, list):
                self._interceptors = [self._interceptors]
        else:
            if not INSTRUMENTATION_ENABLED:
                self._interceptors = None
                self.enabled = False
            else:
                self._interceptors = ["instrumentation"]

        self._interceptor_instances = None
        self._should_save_workflow = save_workflow
        self._workflow_saved = False  # This is to ensure that the wf is saved only once.
        self.current_workflow_id = workflow_id or generate_pseudo_id()
        self.campaign_id = campaign_id or str(uuid4())
        self.workflow_name = workflow_name
        self.workflow_args = workflow_args
        should_delete_buffer_file = (
            flowcept.configs.DELETE_BUFFER_FILE if delete_buffer_file is None else delete_buffer_file
        )
        if should_delete_buffer_file:
            Flowcept.delete_buffer_file()

    def start(self):
        """Start Flowcept Controller."""
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

        self._interceptor_instances: List[BaseInterceptor] = []
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                Flowcept.campaign_id = self.campaign_id
                Flowcept.current_workflow_id = self.current_workflow_id

                interceptor_inst = BaseInterceptor.build(interceptor)
                interceptor_inst.start(bundle_exec_id=self.bundle_exec_id, check_safe_stops=self._check_safe_stops)
                self._interceptor_instances.append(interceptor_inst)
                if isinstance(interceptor_inst._mq_dao.buffer, AutoflushBuffer):
                    Flowcept.buffer = self.buffer = interceptor_inst._mq_dao.buffer.current_buffer
                else:
                    Flowcept.buffer = self.buffer = interceptor_inst._mq_dao.buffer

                if self._should_save_workflow and not self._workflow_saved:
                    self.save_workflow(interceptor, interceptor_inst)

        else:
            Flowcept.current_workflow_id = None
        self.is_started = True
        self.logger.debug("Flowcept started successfully.")
        return self

    def get_buffer(self, return_df: bool = False):
        """
        Retrieve the in-memory message buffer.

        Parameters
        ----------
        return_df : bool, optional
            If False (default), return the raw buffer as a list of dictionaries.
            If True, normalize the buffer into a pandas DataFrame with dotted
            notation for nested keys. Requires ``pandas`` to be installed.

        Returns
        -------
        list of dict or pandas.DataFrame
            - If ``return_df=False``: the buffer as a list of dictionaries.
            - If ``return_df=True``: the buffer as a normalized DataFrame.

        Raises
        ------
        ModuleNotFoundError
            If ``return_df=True`` but ``pandas`` is not installed.

        Examples
        --------
        >>> buf = flowcept.get_buffer()
        >>> isinstance(buf, list)
        True

        >>> df = flowcept.get_buffer(return_df=True)
        >>> "generated.attention" in df.columns
        True
        """
        if return_df:
            try:
                import pandas as pd
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError("pandas is required when return_df=True. Please install pandas.") from e
            return pd.json_normalize(self.buffer, sep=".")
        return self.buffer

    def _publish_buffer(self):
        self._interceptor_instances[0]._mq_dao.bulk_publish(self.buffer)

    def dump_buffer(self, path: str = None):
        """
        Dump the current in-memory buffer to a JSON Lines (JSONL) file.

        Each element of the buffer (a dictionary) is serialized as a single line
        of JSON. If no path is provided, the default path from the settings file
        is used.

        Parameters
        ----------
        path : str, optional
            Destination file path for the JSONL output. If not provided,
            defaults to ``DUMP_BUFFER_PATH`` as configured in the settings.

        Returns
        -------
        None
            The buffer is written to disk, no value is returned.

        Notes
        -----
        - The buffer is expected to be a list of dictionaries.
        - Existing files at the specified path will be overwritten.
        - Logging is performed through the class logger.

        Examples
        --------
        >>> flowcept.dump_buffer("buffer.jsonl")
        # Writes buffer contents to buffer.jsonl

        >>> flowcept.dump_buffer()
        # Writes buffer contents to the default path defined in settings
        """
        if path is None:
            path = DUMP_BUFFER_PATH
        path = resolve_dump_buffer_path(
            path,
            self.current_workflow_id,
            APPEND_WORKFLOW_ID_TO_PATH,
            APPEND_ID_TO_PATH,
        )
        buffer_to_disk(self.buffer, path, self.logger)

    @staticmethod
    def read_buffer_file(
        file_path: str | None = None,
        return_df: bool = False,
        normalize_df: bool = False,
        consolidate: bool = False,
        workflow_id: str | None = None,
        cleanup_files: bool = True,
    ):
        """
        Read a JSON Lines (JSONL) file containing captured Flowcept messages.

        This function loads a file where each line is a serialized JSON object.
        It joins the lines into a single JSON array and parses them efficiently
        with ``orjson``. If ``return_df`` is True, it returns a pandas DataFrame
        created via ``pandas.json_normalize(..., sep='.')`` so nested fields become
        dot-separated columns (for example, ``generated.attention``).

        Parameters
        ----------
        file_path : str, optional
            Path to the buffer file. If not provided, defaults to the value of
            ``DUMP_BUFFER_PATH`` from the configuration. If neither is provided,
            an assertion error is raised.
        return_df : bool, default False
            If True, return a normalized pandas DataFrame. If False, return the
            parsed list of dictionaries.
        normalize_df: bool, default False
            If True, normalize the inner dicts (e.g., used, generated, custom_metadata) as individual columns in the
            returned DataFrame.
        consolidate: bool, default False
            If True, merge all matching workflow buffer files into a single JSONL file first.
        workflow_id : str, optional
            Workflow ID to use when consolidating buffer files.
        cleanup_files : bool, default True
            If True, delete consolidated input files and keep a single JSONL file
            with only the workflow ID appended to the base path.

        Returns
        -------
        list of dict or pandas.DataFrame
            A list of message objects when ``return_df`` is False,
            otherwise a normalized DataFrame with dot-separated columns.

        Raises
        ------
        AssertionError
            If no ``file_path`` is provided and ``DUMP_BUFFER_PATH`` is not set.
        FileNotFoundError
            If the specified file does not exist.
        orjson.JSONDecodeError
            If the file contents cannot be parsed as valid JSON.
        ModuleNotFoundError
            If ``return_df`` is True but pandas is not installed.

        Examples
        --------
        Read messages as a list:

        >>> msgs = read_buffer_file("offline_buffer.jsonl")
        >>> len(msgs) > 0
        True

        Read messages as a normalized DataFrame:

        >>> df = read_buffer_file("offline_buffer.jsonl", return_df=True)
        >>> "generated.attention" in df.columns
        True
        """
        import os
        import orjson

        if file_path is None:
            file_path = DUMP_BUFFER_PATH
        if consolidate:
            if workflow_id is None:
                raise ValueError("workflow_id must be provided when consolidate=True.")
            file_path = Flowcept._consolidate_buffer_file(file_path, workflow_id, cleanup_files=cleanup_files)
        assert file_path is not None, "Please indicate file_path either in the argument or in the config file."
        if not os.path.exists(file_path):
            raise FileNotFoundError(
                f"Flowcept buffer file '{file_path}' was not found. "
                f"Check your settings to see if you're dumping the data to a file and check if you"
                f"have started Flowcept."
            )

        with open(file_path, "rb") as f:
            lines = [ln for ln in f.read().splitlines() if ln]

        buffer: List[Dict[str, Any]] = orjson.loads(b"[" + b",".join(lines) + b"]")

        if return_df:
            try:
                import pandas as pd
            except ModuleNotFoundError as e:
                raise ModuleNotFoundError("pandas is required when return_df=True. Please install pandas.") from e
            if normalize_df:
                return pd.json_normalize(buffer, sep=".")
            else:
                return pd.read_json(file_path, lines=True)

        return buffer

    @staticmethod
    def delete_buffer_file(path: str = None):
        """
        Delete the buffer file from disk if it exists.

        If no path is provided, the default path from the settings file
        is used. Logs whether the file was successfully removed or not found.

        Parameters
        ----------
        path : str, optional
            Path to the buffer JSONL file. If not provided,
            defaults to ``DUMP_BUFFER_PATH`` as configured in the settings.

        Returns
        -------
        None
            The file is deleted from disk if it exists, no value is returned.

        Notes
        -----
        - This operation only affects the file on disk. It does not clear
          the in-memory buffer.
        - Logging is performed through the class logger.

        Examples
        --------
        >>> flowcept.delete_buffer_file("buffer.jsonl")
        # Deletes buffer.jsonl if it exists

        >>> flowcept.delete_buffer_file()
        # Deletes the default buffer file defined in settings
        """
        if path is None:
            path = DUMP_BUFFER_PATH

        try:
            if os.path.exists(path):
                os.remove(path)
                FlowceptLogger().info(f"Buffer file deleted: {path}")
        except Exception as e:
            FlowceptLogger().error(f"Failed to delete buffer file: {path}")
            FlowceptLogger().exception(e)

    @staticmethod
    def _consolidate_buffer_file(path: str, workflow_id: str, cleanup_files: bool = True) -> str:
        """
        Consolidate all buffer files for a workflow into a single JSONL file.

        Parameters
        ----------
        path : str
            Base buffer path (e.g., flowcept_buffer.jsonl).
        workflow_id : str
            Workflow ID to match in buffer filenames.

        Returns
        -------
        str
            Path to the consolidated buffer file.
        """
        base_path = Path(path)
        suffix = base_path.suffix
        name_base = base_path.stem
        pattern = f"{name_base}_{workflow_id}*{suffix}" if suffix else f"{name_base}_{workflow_id}*"
        matches = sorted(base_path.parent.glob(pattern))
        if not matches:
            if base_path.exists():
                return str(base_path)
            raise FileNotFoundError(f"No buffer files found for workflow_id={workflow_id} at {base_path.parent}")
        consolidated_name = f"{name_base}_{workflow_id}{suffix}" if suffix else f"{name_base}_{workflow_id}"
        consolidated_path = base_path.with_name(consolidated_name)

        if matches == [consolidated_path]:
            return str(consolidated_path)

        with open(consolidated_path, "wb") as out_handle:
            for path_obj in matches:
                if path_obj == consolidated_path:
                    continue
                with open(path_obj, "rb") as in_handle:
                    data = in_handle.read()
                    if not data:
                        continue
                    out_handle.write(data)
                    if not data.endswith(b"\n"):
                        out_handle.write(b"\n")

        if cleanup_files:
            removed = 0
            for path_obj in matches:
                if path_obj == consolidated_path:
                    continue
                try:
                    path_obj.unlink()
                    removed += 1
                except Exception:
                    continue
            FlowceptLogger().info(
                f"Consolidated {len(matches)} buffer files into {consolidated_path}. "
                f"Removed {removed} intermediate files."
            )

        return str(consolidated_path)

    def save_workflow(self, interceptor: str, interceptor_instance: BaseInterceptor):
        """
        Save the current workflow and send its metadata using the provided interceptor.

        This method assigns a unique workflow ID if one does not already exist, creates a
        `WorkflowObject`, and populates it with relevant metadata such as campaign ID,
        workflow name, and arguments. The interceptor is then used to send the workflow data.

        Parameters
        ----------
        interceptor : str interceptor kind
        interceptor_instance: BaseInterceptor object to store the workflow info

        Returns
        -------
        None
        """
        wf_obj = WorkflowObject()
        wf_obj.workflow_id = Flowcept.current_workflow_id
        wf_obj.campaign_id = Flowcept.campaign_id

        if self.workflow_name:
            wf_obj.name = self.workflow_name
        if self.workflow_args:
            wf_obj.used = self.workflow_args

        if interceptor == "dask":
            dask_client = self.kwargs.get("dask_client", None)
            if dask_client:
                from flowcept.flowceptor.adapters.dask.dask_plugins import set_workflow_info_on_workers

                wf_obj.adapter_id = "dask"
                scheduler_info = dict(dask_client.scheduler_info())
                wf_obj.custom_metadata = {"n_workers": len(scheduler_info["workers"]), "scheduler": scheduler_info}
                set_workflow_info_on_workers(dask_client, wf_obj)
            else:
                raise Exception("You must provide the argument `dask_client` so we can correctly link the workflow.")

        if KVDB_ENABLED:
            interceptor_instance._mq_dao.set_campaign_id(Flowcept.campaign_id)
        interceptor_instance.send_workflow_message(wf_obj)
        self._workflow_saved = True

    def _init_persistence(self, mq_host=None, mq_port=None):
        if not LMDB_ENABLED and not MONGO_ENABLED:
            return

        from flowcept.flowceptor.consumers.document_inserter import DocumentInserter

        doc_inserter = DocumentInserter(check_safe_stops=self._check_safe_stops, bundle_exec_id=self.bundle_exec_id)
        doc_inserter.start()
        self._db_inserters.append(doc_inserter)

    def stop(self):
        """Stop Flowcept controller."""
        if not self.is_started or not self.enabled:
            self.logger.warning("Flowcept is already stopped or may never have been started!")
            return

        if self._interceptors and len(self._interceptor_instances):
            for interceptor in self._interceptor_instances:
                if interceptor is None:
                    continue
                interceptor.stop(check_safe_stops=self._check_safe_stops)

        if len(self._db_inserters):
            self.logger.info("Stopping DB Inserters...")
            for db_inserter in self._db_inserters:
                db_inserter.stop(bundle_exec_id=self.bundle_exec_id)

        Flowcept.buffer = self.buffer = None
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
        - Logs errors if any service is not ready, and logs success when both services are operational.

        Examples
        --------
        >>> is_alive = services_alive()
        >>> if is_alive:
        ...     print("All services are running.")
        ... else:
        ...     print("One or more services are not ready.")
        """
        logger = FlowceptLogger()
        mq = MQDao.build()
        if MQ_ENABLED:
            if not mq.liveness_test():
                logger.error("MQ Not Ready!")
                return False

        if KVDB_ENABLED:
            if not mq._keyvalue_dao.liveness_test():
                logger.error("KVBD is enabled but is not ready!")
                return False

        logger.info("MQ is alive!")
        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

            if not MongoDBDAO(create_indices=False).liveness_test():
                logger.error("MongoDB is enabled but DocDB is not Ready!")
                return False
            logger.info("DocDB is alive!")
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
