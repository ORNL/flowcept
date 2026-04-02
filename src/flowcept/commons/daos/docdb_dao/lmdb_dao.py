"""lmdb_dao module.

This module provides the `LMDBDAO` class for interacting with an LMDB-backed database.
"""

from time import time
from typing import List, Dict

import lmdb
import json
import pandas as pd

from flowcept import WorkflowObject
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import PERF_LOG, LMDB_SETTINGS
from flowcept.flowceptor.consumers.consumer_utils import curate_dict_task_messages


class LMDBDAO(DocumentDBDAO):
    """DocumentDBDAO implementation for interacting with LMDB.

    Provides methods for storing and retrieving task and workflow data.
    """

    _shared_handles = {}

    def __init__(self):
        # Avoid reopening LMDB for every DAO instance: lmdb can reject
        # opening the same environment path more than once per process.
        self._initialized = False
        self._path = None
        self._open()
        self._initialized = True
        self.logger = FlowceptLogger()

    def _open(self):
        """Open LMDB environment and databases."""
        path = LMDB_SETTINGS.get("path", "flowcept_lmdb")
        handle = LMDBDAO._shared_handles.get(path)
        if handle is None:
            env = lmdb.open(path, map_size=10**12, max_dbs=2)
            handle = {
                "env": env,
                "tasks_db": env.open_db(b"tasks"),
                "workflows_db": env.open_db(b"workflows"),
                "ref_count": 0,
            }
            LMDBDAO._shared_handles[path] = handle

        handle["ref_count"] += 1
        self._path = path
        self._env = handle["env"]
        self._tasks_db = handle["tasks_db"]
        self._workflows_db = handle["workflows_db"]
        self._initialized = True
        self._is_closed = False

    def insert_and_update_many_tasks(self, docs: List[Dict], indexing_key=None):
        """Insert or update multiple task documents in the LMDB database.

        Parameters
        ----------
        docs : list of dict
            A list of task documents to insert or update.
        indexing_key : str, optional
            Key used for indexing task messages.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            t0 = 0
            if PERF_LOG:
                t0 = time()
            indexed_buffer = curate_dict_task_messages(
                docs, indexing_key, t0, convert_times=False, keys_to_drop=["data"]
            )

            with self._env.begin(write=True, db=self._tasks_db) as txn:
                for key, value in indexed_buffer.items():
                    k, v = key.encode(), json.dumps(value).encode()
                    txn.put(k, v)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_one_task(self, task_dict):
        """Insert a single task document.

        Parameters
        ----------
        task_dict : dict
            The task document to insert.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            with self._env.begin(write=True, db=self._tasks_db) as txn:
                k, v = task_dict.get("task_id").encode(), json.dumps(task_dict).encode()
                txn.put(k, v)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_or_update_workflow(self, wf_obj: WorkflowObject):
        """Insert or update a workflow document.

        Parameters
        ----------
        wf_obj : WorkflowObject
            Workflow object to insert or update.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            _dict = wf_obj.to_dict()
            with self._env.begin(write=True, db=self._workflows_db) as txn:
                key = _dict.get("workflow_id").encode()
                value = json.dumps(_dict).encode()
                txn.put(key, value)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_task_keys(self, key_name, keys_list: List[str]) -> bool:
        """Delete task documents by a key value list.

        When deleting by task_id, deletes keys directly. Otherwise, scans
        tasks and deletes matching entries.
        """
        if self._is_closed:
            self._open()
        if type(keys_list) is not list:
            keys_list = [keys_list]
        try:
            with self._env.begin(write=True, db=self._tasks_db) as txn:
                if key_name == "task_id":
                    for key in keys_list:
                        if key is None:
                            continue
                        txn.delete(str(key).encode())
                else:
                    cursor = txn.cursor()
                    for key, value in cursor:
                        entry = json.loads(value.decode())
                        if entry.get(key_name) in keys_list:
                            cursor.delete()
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def count_tasks(self) -> int:
        """Count number of docs in tasks collection."""
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(db=self._tasks_db) as txn:
                return txn.stat().get("entries", 0)
        except Exception as e:
            self.logger.exception(e)
            return -1

    def count_workflows(self) -> int:
        """Count number of docs in workflows collection."""
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(db=self._workflows_db) as txn:
                return txn.stat().get("entries", 0)
        except Exception as e:
            self.logger.exception(e)
            return -1

    @staticmethod
    def _match_filter(entry, filter):
        """
        Check if an entry matches the filter criteria.

        Parameters
        ----------
        entry : dict
            The data entry to check.
        filter : dict
            The filter criteria.

        Returns
        -------
        bool
            True if the entry matches the filter, otherwise False.
        """
        if not filter:
            return True

        for key, value in filter.items():
            if entry.get(key) != value:
                return False
        return True

    def to_df(self, collection="tasks", filter=None) -> pd.DataFrame:
        """Fetch data from LMDB and return a DataFrame with optional MongoDB-style filtering.

        Args:
            collection (str, optional): Collection name. Should be tasks or workflows
            filter (dict, optional): A dictionary representing the filter criteria.
                 Example: {"workflow_id": "123", "status": "completed"}

        Returns
        -------
         pd.DataFrame: A DataFrame containing the filtered data.
        """
        docs = self.query(collection, filter)
        return pd.DataFrame(docs)

    def query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
        collection="tasks",
    ) -> List[Dict]:
        """Query data from LMDB.

        Parameters
        ----------
        filter : dict, optional
            Filter criteria.
        projection : dict, optional
            Fields to include or exclude.
        limit : int, optional
            Maximum number of results to return.
        sort : list, optional
            Sorting criteria.
        aggregation : list, optional
            Aggregation stages.
        remove_json_unserializables : bool, optional
            Remove JSON-unserializable fields.
        collection : str, optional
            Name of the collection ('tasks' or 'workflows'). Default is 'tasks'.

        Returns
        -------
        list of dict
            A list of queried documents.
        """
        if self._is_closed:
            self._open()

        if collection == "tasks":
            _db = self._tasks_db
        elif collection == "workflows":
            _db = self._workflows_db
        else:
            self.logger.warning(f"LMDB does not support collection '{collection}'. Returning None.")
            return None

        try:
            data = []
            with self._env.begin(db=_db) as txn:
                cursor = txn.cursor()
                for key, value in cursor:
                    entry = json.loads(value.decode())
                    if LMDBDAO._match_filter(entry, filter):
                        data.append(entry)
            return data
        except Exception as e:
            self.logger.exception(e)
            return None

    def task_query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
    ):
        """Query tasks collection in the LMDB database.

        Parameters
        ----------
        filter : dict, optional
            Filter criteria for the query.
        projection : dict, optional
            Fields to include or exclude in the results.
        limit : int, optional
            Maximum number of results to return.
        sort : list of tuple, optional
            Sorting criteria. Example: [("field", "asc"), ("field", "desc")].
        aggregation : list, optional
            Aggregation pipeline stages for advanced queries.
        remove_json_unserializables : bool, optional
            Remove JSON-unserializable fields from the results.

        Returns
        -------
        list of dict
            A list of task documents that match the query criteria.
        """
        return self.query(
            collection="tasks",
            filter=filter,
            projection=projection,
            limit=limit,
            sort=sort,
            aggregation=aggregation,
            remove_json_unserializables=remove_json_unserializables,
        )

    def workflow_query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
    ):
        """Query workflows collection in the LMDB database.

        Parameters
        ----------
        filter : dict, optional
            Filter criteria for the query.
        projection : dict, optional
            Fields to include or exclude in the results.
        limit : int, optional
            Maximum number of results to return.
        sort : list of tuple, optional
            Sorting criteria. Example: [("field", "asc"), ("field", "desc")].
        aggregation : list, optional
            Aggregation pipeline stages for advanced queries.
        remove_json_unserializables : bool, optional
            Remove JSON-unserializable fields from the results.

        Returns
        -------
        list of dict
            A list of workflow documents that match the query criteria.
        """
        return self.query(
            collection="workflows",
            filter=filter,
            projection=projection,
            limit=limit,
            sort=sort,
            aggregation=aggregation,
            remove_json_unserializables=remove_json_unserializables,
        )

    def close(self):
        """Close lmdb."""
        if getattr(self, "_initialized"):
            super().close()
            setattr(self, "_initialized", False)
            path = self._path
            handle = LMDBDAO._shared_handles.get(path)
            if handle is not None:
                handle["ref_count"] -= 1
                if handle["ref_count"] <= 0:
                    handle["env"].close()
                    LMDBDAO._shared_handles.pop(path, None)
            self._is_closed = True

    def object_query(self, filter):
        """Query objects collection."""
        raise NotImplementedError

    def get_tasks_recursive(self, workflow_id, max_depth=999, mapping=None):
        """Get_tasks_recursive in LMDB."""
        raise NotImplementedError

    def dump_tasks_to_file_recursive(self, workflow_id, output_file="tasks.parquet", max_depth=999, mapping=None):
        """Dump_tasks_to_file_recursive in LMDB."""
        raise NotImplementedError

    def dump_to_file(self, collection, filter, output_file, export_format, should_zip):
        """Dump data to file."""
        raise NotImplementedError

    def save_or_update_object(
        self,
        object,
        object_id,
        task_id,
        workflow_id,
        type,
        custom_metadata,
        save_data_in_collection,
        pickle_,
        control_version=False,
        tags=None,
    ):
        """Save object."""
        raise NotImplementedError

    def update_object_metadata(
        self,
        object_id,
        custom_metadata=None,
        tags=None,
        type=None,
        task_id=None,
        workflow_id=None,
        control_version=True,
    ):
        """Update object metadata only."""
        raise NotImplementedError

    def get_file_data(self, file_id):
        """Get file data."""
        raise NotImplementedError
