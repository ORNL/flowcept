"""DB API module."""

import uuid
from datetime import datetime
from typing import List, Dict

from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.flowcept_dataclasses.blob_object import BlobObject
from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject
from flowcept.commons.flowcept_logger import FlowceptLogger


class DBAPI(object):
    """DB API class."""

    ASCENDING = 1
    DESCENDING = -1

    # TODO: consider making all methods static
    def __init__(self):
        self.logger = FlowceptLogger()

    @staticmethod
    def _to_message_value(value):
        """Convert object metadata values to MQ-safe values."""
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, bytes):
            return None
        if isinstance(value, dict):
            return {str(k): DBAPI._to_message_value(v) for k, v in value.items() if k not in {"data", "_id"}}
        if isinstance(value, list):
            return [DBAPI._to_message_value(v) for v in value]
        if isinstance(value, tuple):
            return [DBAPI._to_message_value(v) for v in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _emit_object_metadata_message(self, object_id):
        """Emit metadata-only object provenance to the active Flowcept buffer."""
        try:
            dao = DBAPI._dao()
            if hasattr(dao, "get_blob_object_metadata_doc"):
                doc = dao.get_blob_object_metadata_doc(object_id=object_id)
            else:
                doc = self.get_blob_object(object_id=object_id).to_dict()
            if "data" in doc:
                doc["storage_type"] = "in_object"
            elif "grid_fs_file_id" in doc:
                doc["storage_type"] = "gridfs"
            msg = DBAPI._to_message_value(doc)
            msg.pop("_id", None)
            msg.pop("data", None)
            msg["type"] = "object"
            from flowcept.flowcept_api.flowcept_controller import Flowcept

            Flowcept.emit_message(msg)
        except Exception as e:
            self.logger.error(f"Could not emit object metadata message for object_id={object_id}: {e}")

    @classmethod
    def _dao(cls) -> DocumentDBDAO:
        """Return the configured document DAO singleton."""
        return DocumentDBDAO.get_instance(create_indices=False)

    @classmethod
    def get_dao_instance(cls) -> DocumentDBDAO:
        """Return the DAO singleton for internal/advanced operations not on the public API."""
        return cls._dao()

    def close(self):
        """Close DB resources for the active DAO instance."""
        DBAPI._dao().close()

    def liveness_test(self) -> bool:
        """Return True if the configured document store is reachable."""
        return DBAPI._dao().liveness_test()

    @staticmethod
    def db_liveness_tests() -> dict:
        """Return per-backend liveness results for all enabled document stores.

        Tests each enabled backend independently so that both Mongo and LMDB
        are checked when both are enabled (unlike ``liveness_test()``, which
        routes through ``DocumentDBDAO.get_instance()`` and returns one winner).

        Returns
        -------
        dict
            Keys are backend names (``"mongo"``, ``"lmdb"``); values are bool.
        """
        from flowcept.configs import LMDB_ENABLED, MONGO_ENABLED

        results = {}
        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

            results["mongo"] = MongoDBDAO.get_instance(create_indices=False).liveness_test()
        if LMDB_ENABLED:
            from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO

            results["lmdb"] = LMDBDAO.get_instance().liveness_test()
        return results

    def insert_or_update_task(self, task: TaskObject):
        """Insert or update a task document.

        Parameters
        ----------
        task : TaskObject
            Task object to persist.

        Returns
        -------
        Any
            DAO-specific insertion/update return value.
        """
        return DBAPI._dao().insert_one_task(task.to_dict())

    def insert_or_update_workflow(self, workflow_obj: WorkflowObject) -> WorkflowObject:
        """Insert or update a workflow document.

        Parameters
        ----------
        workflow_obj : WorkflowObject
            Workflow object to persist.

        Returns
        -------
        WorkflowObject or None
            The persisted workflow object, or ``None`` on failure.
        """
        if workflow_obj.workflow_id is None:
            workflow_obj.workflow_id = str(uuid.uuid4())
        self.logger.debug(f"DB API going to save workflow {workflow_obj}")
        ret = DBAPI._dao().insert_or_update_workflow(workflow_obj)
        if not ret:
            self.logger.error("Sorry, couldn't update or insert workflow.")
            return None
        else:
            return workflow_obj

    def insert_or_update_agent(self, agent_obj: AgentObject) -> AgentObject:
        """Insert or update an agent document.

        Parameters
        ----------
        agent_obj : AgentObject
            Agent object to persist.

        Returns
        -------
        AgentObject or None
            The persisted agent object, or ``None`` on failure.
        """
        self.logger.debug(f"DB API going to save agent {agent_obj}")
        ret = DBAPI._dao().insert_or_update_agent(agent_obj)
        if not ret:
            self.logger.error("Sorry, couldn't update or insert agent.")
            return None
        else:
            return agent_obj

    def get_workflow_object(self, workflow_id) -> WorkflowObject:
        """Get a workflow object by workflow identifier.

        Parameters
        ----------
        workflow_id : str
            Workflow identifier.

        Returns
        -------
        WorkflowObject or None
            Matching workflow object, or ``None`` when not found.
        """
        wfobs = self.workflow_query(filter={WorkflowObject.workflow_id_field(): workflow_id})
        if wfobs is None:
            self.logger.error("Could not retrieve workflow with that filter.")
            return None
        elif len(wfobs) == 0:
            return None
        else:
            return WorkflowObject.from_dict(wfobs[0])

    def save_workflow_domain_data_schema(self, workflow_id: str, snapshot: Dict) -> bool:
        """Persist a workflow-scoped dynamic schema snapshot."""
        return DBAPI._dao().update_workflow_fields(workflow_id, {"dynamic_schema_snapshot": snapshot})

    def get_workflow_domain_data_schema(self, workflow_id: str) -> Dict | None:
        """Return the persisted dynamic schema snapshot for a workflow."""
        workflow_obj = self.get_workflow_object(workflow_id)
        if workflow_obj is None:
            return None
        return workflow_obj.workflow_domain_data_schema

    def workflow_query(self, filter) -> List[Dict]:
        """Query the ``workflows`` collection.

        Parameters
        ----------
        filter : dict
            Mongo/DAO filter expression.

        Returns
        -------
        list of dict or None
            Matching workflow records, or ``None`` on error.
        """
        results = self.query(collection="workflows", filter=filter)
        if results is None:
            self.logger.error("Could not retrieve workflows with that filter.")
            return None
        return results

    def get_agent_object(self, agent_id) -> AgentObject:
        """Get an agent object by agent identifier.

        Parameters
        ----------
        agent_id : str
            Agent identifier.

        Returns
        -------
        AgentObject or None
            Matching agent object, or ``None`` when not found.
        """
        agobs = self.agent_query(filter={AgentObject.agent_id_field(): agent_id})
        if agobs is None:
            self.logger.error("Could not retrieve agent with that filter.")
            return None
        elif len(agobs) == 0:
            return None
        else:
            return AgentObject.from_dict(agobs[0])

    def agent_query(self, filter) -> List[Dict]:
        """Query the ``agents`` collection.

        Parameters
        ----------
        filter : dict
            Mongo/DAO filter expression.

        Returns
        -------
        list of dict or None
            Matching agent records, or ``None`` on error.
        """
        results = self.query(collection="agents", filter=filter)
        if results is None:
            self.logger.error("Could not retrieve agents with that filter.")
            return None
        return results

    def delete_agents_with_filter(self, filter) -> bool:
        """Delete agents matching the filter.

        Parameters
        ----------
        filter : dict
            DAO filter expression.

        Returns
        -------
        bool
            True if successful, False otherwise.
        """
        dao = DBAPI._dao()
        try:
            return dao.delete_agents_with_filter(filter)
        except Exception as e:
            self.logger.error(f"Could not delete agents with filter {filter}: {e}")
            return False

    def get_tasks_from_current_workflow(self):
        """Get tasks belonging to ``Flowcept.current_workflow_id``.

        Returns
        -------
        list of dict or None
            Matching task records for the active workflow.
        """
        from flowcept.flowcept_api.flowcept_controller import Flowcept

        return self.task_query(filter={"workflow_id": Flowcept.current_workflow_id})

    def task_query(
        self,
        filter: Dict,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """Query the ``tasks`` collection.

        Parameters
        ----------
        filter : dict
            Filter expression used by the backend DAO.
        projection : list or dict, optional
            Fields to include in returned task records.
        limit : int, optional
            Maximum number of records to return.
        sort : list, optional
            Sort expression (field/order pairs).
        aggregation : list, optional
            Aggregation directives supported by the DAO.
        remove_json_unserializables : bool, optional
            Whether to drop known non-JSON-serializable fields.

        Returns
        -------
        list of dict or None
            Matching task records, or ``None`` on error.
        """
        results = self.query(
            collection="tasks",
            filter=filter,
            projection=projection,
            limit=limit,
            sort=sort,
            aggregation=aggregation,
            remove_json_unserializables=remove_json_unserializables,
        )
        if results is None:
            self.logger.error("Could not retrieve tasks with that filter.")
            return None
        return results

    def blob_object_query(self, filter) -> List[Dict]:
        """Query the ``objects`` collection.

        Parameters
        ----------
        filter : dict
            Filter expression for object records.

        Returns
        -------
        list of dict or None
            Matching object documents, or ``None`` on error.
        """
        results = self.query(collection="objects", filter=filter)
        if results is None:
            self.logger.error("Could not retrieve blob objects with that filter.")
            return None
        return results

    def get_blob_object(self, object_id, version=None) -> BlobObject:
        """Get a blob object by ``object_id``.

        Parameters
        ----------
        object_id : str
            Object identifier.
        version : int or None, optional
            ``None`` returns latest from ``objects``.
            Integer version returns the exact version from latest/history.

        Returns
        -------
        BlobObject or None
            The requested blob metadata/object wrapper, or ``None`` if not found.

        Raises
        ------
        ValueError
            If a versioned request is made on a backend without version support.
        """
        dao = DBAPI._dao()
        if hasattr(dao, "get_blob_object_doc"):
            obj_doc = dao.get_blob_object_doc(object_id=object_id, version=version)
        else:
            if version is not None:
                raise ValueError("Versioned blob retrieval is not supported by the configured DB backend.")
            objs = self.blob_object_query(filter={BlobObject.object_id_field(): object_id})
            obj_doc = None if objs is None or len(objs) == 0 else objs[0]

        if obj_doc is None:
            return None
        return BlobObject.from_dict(obj_doc)

    def get_ml_model(self, object_id, version=None) -> BlobObject:
        """Alias to get an ML model blob object.

        Parameters
        ----------
        object_id : str
            Object identifier.
        version : int or None, optional
            ``None`` for latest, integer for exact version.

        Returns
        -------
        BlobObject or None
            Requested ML model blob object.
        """
        return self.get_blob_object(object_id, version=version)

    def ml_model_query(self, filter) -> List[Dict]:
        """Alias to query ML model blob objects.

        Parameters
        ----------
        filter : dict
            Filter expression for object records.

        Returns
        -------
        list of dict or None
            Matching object documents.
        """
        return self.blob_object_query(filter)

    def get_dataset(self, object_id, version=None) -> BlobObject:
        """Alias to get a dataset blob object.

        Parameters
        ----------
        object_id : str
            Object identifier.
        version : int or None, optional
            ``None`` for latest, integer for exact version.

        Returns
        -------
        BlobObject or None
            Requested dataset blob object.
        """
        return self.get_blob_object(object_id, version=version)

    def dataset_query(self, filter) -> List[Dict]:
        """Alias to query dataset blob objects.

        Parameters
        ----------
        filter : dict
            Filter expression for object records.

        Returns
        -------
        list of dict or None
            Matching object documents.
        """
        return self.blob_object_query(filter)

    def get_object_history(self, object_id) -> List[Dict]:
        """Get object version metadata history (latest first, no blob payload).

        Parameters
        ----------
        object_id : str
            Object identifier.

        Returns
        -------
        list of dict
            Version metadata records sorted by descending version.

        Raises
        ------
        ValueError
            If version listing is unavailable for the active backend.
        """
        dao = DBAPI._dao()
        if hasattr(dao, "get_object_history"):
            return dao.get_object_history(object_id)
        if not hasattr(dao, "list_object_versions"):
            raise ValueError("Version listing is not supported by the configured DB backend.")
        return dao.list_object_versions(object_id)

    def list_object_versions(self, object_id) -> List[Dict]:
        """Backward-compatible alias to ``get_object_history``."""
        return self.get_object_history(object_id)

    def get_blob_fingerprint(self, object_id, version=None) -> Dict:
        """Get a lightweight blob fingerprint for equality checks.

        Parameters
        ----------
        object_id : str
            Object identifier.
        version : int or None, optional
            ``None`` for latest version, integer for an exact version.

        Returns
        -------
        dict
            Metadata-only fingerprint with hash and size fields.
        """
        dao = DBAPI._dao()
        if hasattr(dao, "get_blob_object_metadata_doc"):
            doc = dao.get_blob_object_metadata_doc(object_id=object_id, version=version)
        else:
            # Fallback for backends without dedicated metadata retrieval.
            doc = self.get_blob_object(object_id=object_id, version=version).to_dict()
            doc.pop("data", None)

        return {
            "object_id": doc.get("object_id"),
            "version": int(doc.get("version", 0)),
            "object_size_bytes": doc.get("object_size_bytes"),
            "data_sha256": doc.get("data_sha256"),
            "data_hash_algo": doc.get("data_hash_algo"),
            "storage_type": "in_object" if "grid_fs_file_id" not in doc else "gridfs",
        }

    def blob_objects_equal(
        self,
        object_id_a,
        object_id_b,
        version_a=None,
        version_b=None,
        fallback_to_payload=False,
    ) -> bool:
        """Compare two blob objects by persisted payload identity metadata.

        Parameters
        ----------
        object_id_a : str
            First object identifier.
        object_id_b : str
            Second object identifier.
        version_a : int or None, optional
            Version of the first object. ``None`` means latest.
        version_b : int or None, optional
            Version of the second object. ``None`` means latest.
        fallback_to_payload : bool, optional
            If ``True`` and hash metadata is unavailable, compare loaded payload bytes.

        Returns
        -------
        bool
            ``True`` when objects are equivalent under the selected strategy, else ``False``.
        """
        fp_a = self.get_blob_fingerprint(object_id=object_id_a, version=version_a)
        fp_b = self.get_blob_fingerprint(object_id=object_id_b, version=version_b)

        hash_a = fp_a.get("data_sha256")
        hash_b = fp_b.get("data_sha256")
        algo_a = fp_a.get("data_hash_algo")
        algo_b = fp_b.get("data_hash_algo")

        if hash_a and hash_b and algo_a == algo_b:
            return hash_a == hash_b

        size_a = fp_a.get("object_size_bytes")
        size_b = fp_b.get("object_size_bytes")
        if size_a is not None and size_b is not None and size_a != size_b:
            return False

        if not fallback_to_payload:
            return False

        data_a = getattr(self.get_blob_object(object_id_a, version=version_a), "data", None)
        data_b = getattr(self.get_blob_object(object_id_b, version=version_b), "data", None)
        return data_a == data_b

    def get_tasks_recursive(self, workflow_id, max_depth=999, mapping=None):
        """
        Retrieve all tasks recursively for a given workflow ID.

        This method fetches a workflow's root task and all its child tasks recursively
        using the data access object (DAO). The recursion depth can be controlled
        using the `max_depth` parameter to prevent excessive recursion.

        Parameters
        ----------
        workflow_id : str
            The ID of the workflow for which tasks need to be retrieved.
        max_depth : int, optional
            The maximum depth to traverse in the task hierarchy (default is 999).
            Helps avoid excessive recursion for workflows with deeply nested tasks.

        Returns
        -------
        list of dict
            A list of tasks represented as dictionaries, including parent and child tasks
            up to the specified recursion depth.

        Raises
        ------
        Exception
            If an error occurs during retrieval, it is logged and re-raised.

        Notes
        -----
        This method delegates the operation to the DAO implementation.
        """
        try:
            return DBAPI._dao().get_tasks_recursive(workflow_id, max_depth, mapping)
        except Exception as e:
            self.logger.exception(e)
            raise e

    def dump_tasks_to_file_recursive(self, workflow_id, output_file="tasks.parquet", max_depth=999, mapping=None):
        """
        Dump tasks recursively for a given workflow ID to a file.

        This method retrieves all tasks (parent and children) for the given workflow ID
        up to a specified recursion depth and saves them to a file in Parquet format.

        Parameters
        ----------
        workflow_id : str
            The ID of the workflow for which tasks need to be retrieved and saved.
        output_file : str, optional
            The name of the output file to save tasks (default is "tasks.parquet").
        max_depth : int, optional
            The maximum depth to traverse in the task hierarchy (default is 999).
            Helps avoid excessive recursion for workflows with deeply nested tasks.

        Returns
        -------
        None

        Raises
        ------
        Exception
            If an error occurs during the file dump operation, it is logged and re-raised.

        Notes
        -----
        The method delegates the task retrieval and saving operation to the DAO implementation.
        """
        try:
            return DBAPI._dao().dump_tasks_to_file_recursive(workflow_id, output_file, max_depth, mapping)
        except Exception as e:
            self.logger.exception(e)
            raise e

    def dump_to_file(
        self,
        collection="tasks",
        filter=None,
        output_file=None,
        export_format="json",
        should_zip=False,
    ):
        """Export data from a collection to a file.

        Parameters
        ----------
        collection : str, optional
            Collection name to dump.
        filter : dict, optional
            Filter expression for selecting records.
        output_file : str, optional
            Output file path.
        export_format : str, optional
            Export format supported by backend DAO.
        should_zip : bool, optional
            Whether output should be compressed.

        Returns
        -------
        bool
            ``True`` on success, ``False`` on validation or DAO errors.
        """
        if filter is None and not should_zip:
            self.logger.error("Not allowed to dump entire database without filter and without zipping it.")
            return False
        try:
            DBAPI._dao().dump_to_file(
                collection,
                filter,
                output_file,
                export_format,
                should_zip,
            )
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def save_or_update_object(
        self,
        object,
        object_id=None,
        task_id=None,
        workflow_id=None,
        object_type=None,
        custom_metadata=None,
        save_data_in_collection=False,
        pickle=False,
        control_version=False,
        tags=None,
    ):
        """Save or update a blob object.

        Parameters
        ----------
        object : Any
            Blob payload bytes or serializable object.
        object_id : str, optional
            Logical object identifier. Generated when omitted.
        task_id : str, optional
            Associated task identifier.
        workflow_id : str, optional
            Associated workflow identifier. Defaults to current workflow when available.
        object_type : str, optional
            User-defined object category.
        custom_metadata : dict, optional
            Arbitrary metadata attached to the object.
        save_data_in_collection : bool, optional
            ``True`` stores bytes in-object (``data`` field in ``objects``).
            ``False`` stores payload in GridFS and keeps pointer in metadata.
        pickle : bool, optional
            If ``True``, pickle ``object`` before persistence.
        control_version : bool, optional
            If ``True``, enable append-only history semantics via ``object_history``.
        tags : list of str, optional
            Labels to associate with the object.

        Returns
        -------
        str
            Persisted object identifier.
        """
        if workflow_id is None:
            try:
                from flowcept.flowcept_api.flowcept_controller import Flowcept

                workflow_id = Flowcept.current_workflow_id
            except Exception:
                workflow_id = None
        object_id = DBAPI._dao().save_or_update_object(
            object,
            object_id,
            task_id,
            workflow_id,
            object_type,
            custom_metadata,
            save_data_in_collection=save_data_in_collection,
            pickle_=pickle,
            control_version=control_version,
            tags=tags,
        )
        self._emit_object_metadata_message(object_id)
        return object_id

    def update_object_metadata(
        self,
        object_id,
        custom_metadata=None,
        tags=None,
        object_type=None,
        task_id=None,
        workflow_id=None,
        control_version=True,
    ):
        """Update object metadata without rewriting object payload bytes.

        Parameters
        ----------
        object_id : str
            Logical object identifier to update.
        custom_metadata : dict, optional
            Metadata dictionary to set.
        tags : list of str, optional
            Tags to set.
        object_type : str, optional
            Object type/category to set.
        task_id : str, optional
            Task identifier to set.
        workflow_id : str, optional
            Workflow identifier to set.
        control_version : bool, optional
            If ``True`` (default), append history and increment version.

        Returns
        -------
        str
            Updated object identifier.
        """
        updated_object_id = DBAPI._dao().update_object_metadata(
            object_id=object_id,
            custom_metadata=custom_metadata,
            tags=tags,
            object_type=object_type,
            task_id=task_id,
            workflow_id=workflow_id,
            control_version=control_version,
        )
        self._emit_object_metadata_message(updated_object_id)
        return updated_object_id

    def to_df(self, collection="tasks", filter=None):
        """Query a collection and return a pandas DataFrame.

        Parameters
        ----------
        collection : str, optional
            Collection name to convert.
        filter : dict, optional
            Filter expression.

        Returns
        -------
        pandas.DataFrame
            DataFrame generated by DAO backend.
        """
        return DBAPI._dao().to_df(collection, filter)

    def query(
        self,
        filter=None,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
        collection="tasks",
    ):
        """Run a generic query against a collection.

        Parameters
        ----------
        filter : dict, optional
            Filter expression.
        projection : list or dict, optional
            Projected fields to include.
        limit : int, optional
            Maximum number of records.
        sort : list, optional
            Sort expression.
        aggregation : list, optional
            Aggregation directives.
        remove_json_unserializables : bool, optional
            Drop known non-JSON-serializable fields where supported.
        collection : str, optional
            Target collection name.

        Returns
        -------
        list of dict
            Query results from the backend DAO; empty list when nothing matches or on error.
        """
        result = DBAPI._dao().query(
            filter, projection, limit, sort, aggregation, remove_json_unserializables, collection
        )
        return result or []

    def save_or_update_ml_model(
        self,
        object,
        object_id=None,
        task_id=None,
        workflow_id=None,
        object_type="ml_model",
        custom_metadata=None,
        save_data_in_collection=False,
        pickle=False,
        control_version=False,
        tags=None,
    ):
        """Alias to save or update ML model blobs.

        Parameters
        ----------
        object : Any
            Model payload bytes/object.
        object_id : str, optional
            Logical object identifier.
        task_id : str, optional
            Associated task identifier.
        workflow_id : str, optional
            Associated workflow identifier.
        object_type : str, optional
            Category label. Defaults to ``"ml_model"``.
        custom_metadata : dict, optional
            Custom metadata.
        save_data_in_collection : bool, optional
            In-object data storage toggle (``data`` field in ``objects``).
        pickle : bool, optional
            Pickle before storage.
        control_version : bool, optional
            Enable append-only history semantics.
        tags : list of str, optional
            Labels to associate with the object.

        Returns
        -------
        str
            Persisted object identifier.
        """
        return self.save_or_update_object(
            object=object,
            object_id=object_id,
            task_id=task_id,
            workflow_id=workflow_id,
            object_type=object_type,
            custom_metadata=custom_metadata,
            save_data_in_collection=save_data_in_collection,
            pickle=pickle,
            control_version=control_version,
            tags=tags,
        )

    def save_or_update_dataset(
        self,
        object,
        object_id=None,
        task_id=None,
        workflow_id=None,
        object_type="dataset",
        custom_metadata=None,
        save_data_in_collection=False,
        pickle=False,
        control_version=False,
        tags=None,
    ) -> str:
        """Alias to save or update dataset blobs.

        Parameters
        ----------
        object : Any
            Dataset payload bytes/object.
        object_id : str, optional
            Logical object identifier.
        task_id : str, optional
            Associated task identifier.
        workflow_id : str, optional
            Associated workflow identifier.
        object_type : str, optional
            Category label. Defaults to ``"dataset"``.
        custom_metadata : dict, optional
            Custom metadata.
        save_data_in_collection : bool, optional
            In-object data storage toggle (``data`` field in ``objects``).
        pickle : bool, optional
            Pickle before storage.
        control_version : bool, optional
            Enable append-only history semantics.
        tags : list of str, optional
            Labels to associate with the object.

        Returns
        -------
        str
            Persisted object identifier.
        """
        return self.save_or_update_object(
            object=object,
            object_id=object_id,
            task_id=task_id,
            workflow_id=workflow_id,
            object_type=object_type,
            custom_metadata=custom_metadata,
            save_data_in_collection=save_data_in_collection,
            pickle=pickle,
            control_version=control_version,
            tags=tags,
        )

    def save_or_update_torch_model(
        self,
        model,
        object_id=None,
        task_id=None,
        workflow_id=None,
        custom_metadata=None,
        control_version=False,
        save_profile=True,
        tags=None,
    ) -> str:
        """Save a PyTorch model state dictionary as an object blob.

        Parameters
        ----------
        model : torch.nn.Module
            PyTorch model whose ``state_dict`` will be persisted.
        object_id : str, optional
            Existing object identifier to update.
        task_id : str, optional
            Associated task identifier.
        workflow_id : str, optional
            Associated workflow identifier.
        custom_metadata : dict, optional
            Extra metadata. The model class name is added automatically.
        control_version : bool, optional
            Enable append-only history semantics when updating an existing
            logical object id.
        save_profile : bool, optional
            If ``True`` (default), adds ``model_profile`` to
            ``custom_metadata`` using Flowcept PyTorch profiling.
        tags : list of str, optional
            Labels to associate with the object.

        Returns
        -------
        str
            Persisted object identifier.
        """
        import torch
        import io

        state_dict = model.state_dict()
        buffer = io.BytesIO()
        torch.save(state_dict, buffer)
        buffer.seek(0)
        binary_data = buffer.read()
        if custom_metadata is None:
            custom_metadata = {}
        model_profile = {}
        if save_profile:
            from flowcept.instrumentation.flowcept_torch import get_torch_model_profile

            model_profile = {"model_profile": get_torch_model_profile(model)}
        cm = {
            **custom_metadata,
            **model_profile,
            "class": model.__class__.__name__,
        }
        obj_id = self.save_or_update_object(
            object=binary_data,
            object_id=object_id,
            object_type="ml_model",
            task_id=task_id,
            workflow_id=workflow_id,
            custom_metadata=cm,
            control_version=control_version,
            tags=tags,
        )

        return obj_id

    def load_torch_model(self, model, object_id: str):
        """Load a stored PyTorch model state dict into a model instance.

        Parameters
        ----------
        model : torch.nn.Module
            Target model instance to receive the persisted state dict.
        object_id : str
            Object identifier in ``objects``.

        Returns
        -------
        dict
            Object document used to load the model.

        Notes
        -----
        This method also attaches ``model._flowcept_model_object`` with object
        metadata only (all available fields except blob bytes in ``data``).
        """
        import torch
        import io

        doc = self.query(collection="objects", filter={"object_id": object_id})[0]

        if "data" in doc:
            binary_data = doc["data"]
        else:
            file_id = doc["grid_fs_file_id"]
            binary_data = DBAPI._dao().get_file_data(file_id)

        buffer = io.BytesIO(binary_data)
        state_dict = torch.load(buffer, weights_only=True)
        model.load_state_dict(state_dict)
        model._flowcept_model_object = {k: v for k, v in doc.items() if k != "data"}

        return doc

    def save_node_positions(self, workflow_id: str, graph_type: str, positions: dict) -> bool:
        """Save node positions for a workflow graph type.

        Parameters
        ----------
        workflow_id : str
            Workflow identifier.
        graph_type : str
            Graph type: 'dataflow', 'task', or 'activity'.
        positions : dict
            Dict mapping node IDs to coordinates.

        Returns
        -------
        bool
            True on success, False otherwise.
        """
        dao = DBAPI._dao()
        if hasattr(dao, "save_node_positions"):
            return dao.save_node_positions(workflow_id, graph_type, positions)
        return False

    def get_node_positions(self, workflow_id: str, graph_type: str) -> dict:
        """Get node positions for a workflow graph type.

        Parameters
        ----------
        workflow_id : str
            Workflow identifier.
        graph_type : str
            Graph type.

        Returns
        -------
        dict
            Dict mapping node IDs to coordinates.
        """
        dao = DBAPI._dao()
        if hasattr(dao, "get_node_positions"):
            return dao.get_node_positions(workflow_id, graph_type)
        return {}

    def task_summary(self, filter: Dict) -> Dict:
        """Summarize tasks: status counts, per-activity stats, and time range."""
        return DBAPI._dao().task_summary(filter)

    def derive_campaigns(self, campaign_id: str = None) -> List[Dict]:
        """Derive campaign summaries by grouping workflows and tasks by campaign_id."""
        return DBAPI._dao().derive_campaigns(campaign_id=campaign_id)

    def derive_agents(self, filter: Dict = None) -> List[Dict]:
        """Derive agent summaries by joining stored agents with task provenance."""
        return DBAPI._dao().derive_agents(filter)

    def telemetry_timeseries(
        self, filter: Dict, fields: List, x_field: str = "started_at", limit: int = 1000
    ) -> List[Dict]:
        """Extract plottable rows of dot-notated fields from tasks."""
        return DBAPI._dao().telemetry_timeseries(filter, fields, x_field=x_field, limit=limit)

    def resolve_chart_data(self, data: Dict, context: Dict = None) -> Dict:
        """Resolve a declarative chart spec into plottable rows."""
        return DBAPI._dao().resolve_chart_data(data, context=context)

    def delete_object_keys(self, key_name: str, keys_list: List) -> bool:
        """Delete object documents matching key_name/keys_list. Raises NotImplementedError if unsupported."""
        dao = DBAPI._dao()
        if not hasattr(dao, "delete_object_keys"):
            raise NotImplementedError("delete_object_keys is not supported by the active DB backend.")
        return dao.delete_object_keys(key_name, keys_list)

    def delete_workflow_data(self, workflow_id: str) -> dict:
        """Delete all data for a workflow. Returns empty dict if unsupported."""
        dao = DBAPI._dao()
        if not hasattr(dao, "delete_workflow_data"):
            return {}
        return dao.delete_workflow_data(workflow_id)

    def delete_campaign_data(self, campaign_id: str) -> dict:
        """Delete all data for a campaign. Returns empty dict if unsupported."""
        dao = DBAPI._dao()
        if not hasattr(dao, "delete_campaign_data"):
            return {}
        return dao.delete_campaign_data(campaign_id)
