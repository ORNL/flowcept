"""DocumentDBDAO module.

This module provides an abstract base class `DocumentDBDAO` for document-based database operations.
"""

from typing import List, Dict

import pandas as pd


from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import MONGO_ENABLED, LMDB_ENABLED


class DocumentDBDAO(object):
    """Abstract class for document database operations.

    Provides an interface for interacting with document databases, supporting operations
    such as insertion, updates, queries, and data export.
    """

    _instances = {}

    def __new__(cls, *args, **kwargs) -> "DocumentDBDAO":
        """Ensure singleton behavior for the `DocumentDBDAO` class.

        Returns
        -------
        DocumentDBDAO
           A singleton instance of the class.
        """
        if cls not in cls._instances:
            instance = super().__new__(cls)
            cls._instances[cls] = instance
        return cls._instances[cls]

    def __init__(self, *args, **kwargs):
        """Initialize the `DocumentDBDAO` class."""
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self.logger = FlowceptLogger()
            self._init(*args, **kwargs)

    @staticmethod
    def build(*args, **kwargs) -> "DocumentDBDAO":
        """Build a `DocumentDBDAO` instance for querying.

        Depending on the configuration, this method creates an instance of
        either MongoDBDAO or LMDBDAO.

        Parameters
        ----------
        *args : tuple
            Positional arguments for DAO initialization.
        **kwargs : dict
            Keyword arguments for DAO initialization.

        Returns
        -------
        DocumentDBDAO
            An instance of a concrete `DocumentDBDAO` subclass.

        Raises
        ------
        NotImplementedError
            If neither MongoDB nor LMDB is enabled.
        """
        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

            return MongoDBDAO(*args, **kwargs)
        elif LMDB_ENABLED:
            from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO

            return LMDBDAO(*args, **kwargs)
        else:
            raise NotImplementedError

    def _init(self, *args, **kwargs):
        """Initialize subclass-specific properties.

        To be implemented by subclasses.

        Parameters
        ----------
        *args : tuple
            Positional arguments for subclass initialization.
        **kwargs : dict
            Keyword arguments for subclass initialization.
        """
        raise NotImplementedError

    def insert_and_update_many_tasks(self, docs: List[Dict], indexing_key=None):
        """Insert or update multiple task documents.

        Parameters
        ----------
        docs : List[Dict]
            List of task documents to insert or update.
        indexing_key : str, optional
            Key to use for indexing documents.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def insert_or_update_workflow(self, wf_obj: WorkflowObject):
        """Insert or update a workflow object.

        Parameters
        ----------
        wf_obj : WorkflowObject
            The workflow object to insert or update.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def insert_one_task(self, task_dict: Dict):
        """Insert a single task document.

        Parameters
        ----------
        task_dict : Dict
            Task document to insert.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def to_df(self, collection, filter=None) -> pd.DataFrame:
        """Convert a collection to a pandas DataFrame.

        Parameters
        ----------
        collection : str
            The name of the collection to query.
        filter : dict, optional
            Query filter to apply.

        Returns
        -------
        pd.DataFrame
            The resulting DataFrame.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def query(
        self, collection, filter, projection, limit, sort, aggregation, remove_json_unserializables
    ):
        """Query a collection.

        Parameters
        ----------
        collection : str
            The name of the collection to query.
        filter : dict
            Query filter.
        projection : dict
            Fields to include or exclude.
        limit : int
            Maximum number of documents to return.
        sort : list
            Sorting order.
        aggregation : list
            Aggregation pipeline stages.
        remove_json_unserializables : bool
            Whether to remove JSON-unserializable fields.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def task_query(self, filter, projection, limit, sort, aggregation, remove_json_unserializables):
        """Query task documents.

        Parameters
        ----------
        filter : dict
            Query filter to apply.
        projection : dict
            Fields to include or exclude in the results.
        limit : int
            Maximum number of documents to return.
        sort : list
            Sorting criteria.
        aggregation : list
            Aggregation pipeline stages.
        remove_json_unserializables : bool
            Whether to remove JSON-unserializable fields from the results.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def workflow_query(self, filter, projection, limit, sort, remove_json_unserializables):
        """Query workflow documents.

        Parameters
        ----------
        filter : dict
            Query filter to apply.
        projection : dict
            Fields to include or exclude in the results.
        limit : int
            Maximum number of documents to return.
        sort : list
            Sorting criteria.
        remove_json_unserializables : bool
            Whether to remove JSON-unserializable fields from the results.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def object_query(self, filter):
        """Query objects based on the specified filter.

        Parameters
        ----------
        filter : dict
            Query filter to apply.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def dump_to_file(self, collection_name, filter, output_file, export_format, should_zip):
        """Export a collection's data to a file.

        Parameters
        ----------
        collection_name : str
            Name of the collection to export.
        filter : dict
            Query filter to apply.
        output_file : str
            Path to the output file.
        export_format : str
            Format of the exported file (e.g., JSON, CSV).
        should_zip : bool
            Whether to compress the output file into a ZIP archive.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def save_object(
        self,
        object,
        object_id,
        task_id,
        workflow_id,
        type,
        custom_metadata,
        save_data_in_collection,
        pickle_,
    ):
        """Save an object with associated metadata.

        Parameters
        ----------
        object : Any
            The object to save.
        object_id : str
            Unique identifier for the object.
        task_id : str
            Task ID associated with the object.
        workflow_id : str
            Workflow ID associated with the object.
        type : str
            Type of the object.
        custom_metadata : dict
            Custom metadata to associate with the object.
        save_data_in_collection : bool
            Whether to save the object in a database collection.
        pickle_ : bool
            Whether to serialize the object using pickle.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def close(self):
        """Close database connections and release resources.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError

    def get_file_data(self, file_id):
        """Retrieve file data by file ID.

        Parameters
        ----------
        file_id : str
            Unique identifier of the file.

        Raises
        ------
        NotImplementedError
            This method must be implemented by subclasses.
        """
        raise NotImplementedError
