"""DocumentDBDAO module.

This module provides an abstract base class `DocumentDBDAO` for document-based database operations.
"""

from abc import ABC, abstractmethod
from typing import List, Dict

import pandas as pd


from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
from flowcept.configs import MONGO_ENABLED, LMDB_ENABLED


class DocumentDBDAO(ABC):
    """Abstract class for document database operations.

    Provides an interface for interacting with document databases, supporting operations
    such as insertion, updates, queries, and data export.
    """

    _instance: "DocumentDBDAO" = None

    @staticmethod
    def get_instance(*args, **kwargs) -> "DocumentDBDAO":
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
        if DocumentDBDAO._instance is not None:
            if hasattr(DocumentDBDAO._instance, "_initialized"):
                return DocumentDBDAO._instance
            else:
                DocumentDBDAO._instance.close()
                raise Exception(
                    "This should not happen. "
                    "If instance is not None and Not initialized,"
                    " this is an inconsistent state."
                    " We are forcefully fixing the state now:"
                )

        if MONGO_ENABLED:
            from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

            DocumentDBDAO._instance = MongoDBDAO(*args, **kwargs)
        elif LMDB_ENABLED:
            from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO

            DocumentDBDAO._instance = LMDBDAO()
        else:
            raise Exception("All dbs are disabled. You can't use this.")
        # TODO: revise, this below may be better in subclasses
        DocumentDBDAO._instance._initialized = True
        return DocumentDBDAO._instance

    def close(self):
        """Close DAO connections and release resources."""
        del DocumentDBDAO._instance
        DocumentDBDAO._instance = None

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    def query(self, filter, projection, limit, sort, aggregation, remove_json_unserializables, collection):
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
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

    @abstractmethod
    def get_tasks_recursive(self, workflow_id, max_depth=999):
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
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
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

    @abstractmethod
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
