"""lmdb_dao module."""
from typing import List, Dict

import pandas as pd


from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import MONGO_ENABLED, LMDB_ENABLED


class DocumentDBDAO(object):
    """Key value DAO class."""

    _instances = {}

    def __new__(cls, *args, **kwargs) -> "DocumentDBDAO":
        """Singleton creator for DocumentDAO."""
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
        return cls._instances[cls]

    def __init__(self, *args, **kwargs):
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.logger = FlowceptLogger()
            self._init(*args, **kwargs)

    @staticmethod
    def build(*args, **kwargs) -> "DocumentDBDAO":
        """Build a DocumentDBDAO instance. Use it only for querying."""
        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
            return MongoDBDAO(*args, **kwargs)
        elif LMDB_ENABLED:
            from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO
            return LMDBDAO(*args, **kwargs)
        else:
            raise NotImplementedError

    def _init(self, *args, **kwargs):
        raise NotImplementedError

    def insert_and_update_many_tasks(self, docs: List[Dict], indexing_key=None):
        raise NotImplementedError

    def insert_or_update_workflow(self, wf_obj: WorkflowObject):
        raise NotImplementedError

    def insert_one_task(self, task_dict: Dict):
        raise NotImplementedError

    def to_df(self, collection, filter=None) -> pd.DataFrame:
        raise NotImplementedError

    def query(self, collection, filter, projection, limit, sort, aggregation, remove_json_unserializables):
        raise NotImplementedError

    def task_query(self, filter, projection, limit, sort, aggregation, remove_json_unserializables):
        raise NotImplementedError

    def workflow_query(self, filter, projection, limit, sort, remove_json_unserializables):
        raise NotImplementedError

    def object_query(self, filter):
        raise NotImplementedError

    def dump_to_file(self, collection_name, filter, output_file, export_format, should_zip):
        raise NotImplementedError

    def save_object(self, object, object_id, task_id, workflow_id, type, custom_metadata,
                    save_data_in_collection, pickle_):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def get_file_data(self, file_id):
        raise NotImplementedError


