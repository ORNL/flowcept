"""lmdb_dao module."""
from time import time
from typing import List, Dict

import lmdb
import json
import pandas as pd

from flowcept import WorkflowObject
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.configs import PERF_LOG, DATABASES
from flowcept.flowceptor.consumers.consumer_utils import curate_dict_task_messages


class LMDBDAO(DocumentDBDAO):
    """Key value DAO class."""

    def _init(self, *args, **kwargs):
        self._open()

    def _open(self):
        _path = DATABASES.get("lmdb").get("path", "lmdb")
        self._env = lmdb.open(_path, map_size=10 ** 9, max_dbs=2)
        self._tasks_db = self._env.open_db(b'tasks')
        self._workflows_db = self._env.open_db(b'workflows')
        self._is_closed = False

    def insert_and_update_many_tasks(self, docs: List[Dict], indexing_key=None):
        try:
            t0 = 0
            if PERF_LOG:
                t0 = time()
            indexed_buffer = curate_dict_task_messages(docs, indexing_key, t0, convert_times=False)
            with self._env.begin(write=True, db=self._tasks_db) as txn:
                for key, value in indexed_buffer.items():
                    k, v = key.encode(), json.dumps(value).encode()
                    txn.put(k, v)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_one_task(self, task_dict):
        try:
            with self._env.begin(write=True, db=self._tasks_db) as txn:
                k, v = task_dict.get("task_id").encode(), json.dumps(task_dict).encode()
                txn.put(k, v)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_or_update_workflow(self, wf_obj: WorkflowObject):
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

    @staticmethod
    def _match_filter(entry, filter):
        """
        Checks if an entry matches the filter criteria.

        Args:
            entry (dict): The data entry to check.
            filter (dict): The filter criteria.

        Returns:
            bool: True if the entry matches the filter, otherwise False.
        """
        if not filter:
            return True

        for key, value in filter.items():
            if entry.get(key) != value:
                return False
        return True

    def to_df(self, collection="tasks", filter=None) -> pd.DataFrame:
        """
        Fetches data from LMDB and transforms it into a pandas DataFrame with optional MongoDB-style filtering.

        Args:
            collection (str, optional): Collection name. Should be tasks or workflows
            filter (dict, optional): A dictionary representing the filter criteria.
                 Example: {"workflow_id": "123", "status": "completed"}

        Returns:
         pd.DataFrame: A DataFrame containing the filtered data.
        """
        docs = self.query(collection,filter)
        return pd.DataFrame(docs)

    def query(self, collection="tasks", filter=None, projection=None, limit=None, sort=None, aggregation=None,
              remove_json_unserializables=None) -> List[Dict]:
        if self._is_closed:
            self._open()

        if collection == "tasks":
            _db = self._tasks_db
        elif collection == "workflows":
            _db = self._workflows_db
        else:
            msg = f"Only tasks and workflows "
            raise Exception(msg + "collections are currently available for this.")

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
        finally:
            self.close()

    def task_query(self, filter=None, projection=None, limit=None, sort=None, aggregation=None, remove_json_unserializables=None):
        return self.query(collection="tasks", filter=filter, projection=projection, limit=limit, sort=sort, aggregation=aggregation, remove_json_unserializables=remove_json_unserializables)

    def workflow_query(self, filter=None, projection=None, limit=None, sort=None, aggregation=None, remove_json_unserializables=None):
        return self.query(collection="workflows", filter=filter, projection=projection, limit=limit, sort=sort, aggregation=aggregation, remove_json_unserializables=remove_json_unserializables)

    def close(self):
        return
        self._env.close()
        self._is_closed = True
