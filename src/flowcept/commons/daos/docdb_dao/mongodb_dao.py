"""Document DB interaction module."""

from typing import List, Dict, Tuple, Any
import io
import json
from uuid import uuid4

import pickle
import zipfile

import pandas as pd
from bson import ObjectId
from bson.json_util import dumps
from pymongo import MongoClient, UpdateOne

from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.utils import perf_log, get_utc_now_str
from flowcept.configs import PERF_LOG, MONGO_CREATE_INDEX
from flowcept.flowceptor.consumers.consumer_utils import (
    curate_dict_task_messages,
)
from time import time


class MongoDBDAO(DocumentDBDAO):
    """
    A data access object for MongoDB.

    This class encapsulates common operations for interacting with MongoDB,
    including querying, inserting, updating, and deleting documents across
    various collections (`tasks`, `workflows`, `objects`).
    """

    def __new__(cls, *args, **kwargs) -> "MongoDBDAO":
        """Singleton creator for MongoDBDAO."""
        # Check if an instance already exists
        if DocumentDBDAO._instance is None:
            DocumentDBDAO._instance = super(MongoDBDAO, cls).__new__(cls)
        return DocumentDBDAO._instance

    def __init__(self, create_indices=MONGO_CREATE_INDEX):
        if not hasattr(self, "_initialized"):
            from flowcept.configs import (
                MONGO_HOST,
                MONGO_PORT,
                MONGO_DB,
                MONGO_URI,
            )

            self._initialized = True
            self.logger = FlowceptLogger()

            if MONGO_URI is not None:
                self._client = MongoClient(MONGO_URI)
            else:
                self._client = MongoClient(MONGO_HOST, MONGO_PORT)
            self._db = self._client[MONGO_DB]

            self._tasks_collection = self._db["tasks"]
            self._wfs_collection = self._db["workflows"]
            self._obj_collection = self._db["objects"]

            if create_indices:
                self._create_indices()

    def _create_indices(self):
        # Creating task collection indices:
        existing_indices = [list(x["key"].keys())[0] for x in self._tasks_collection.list_indexes()]
        if TaskObject.task_id_field() not in existing_indices:
            self._tasks_collection.create_index(TaskObject.task_id_field(), unique=True)
        if TaskObject.workflow_id_field() not in existing_indices:
            self._tasks_collection.create_index(TaskObject.workflow_id_field())

        # Creating workflow collection indices:
        existing_indices = [list(x["key"].keys())[0] for x in self._wfs_collection.list_indexes()]
        if WorkflowObject.workflow_id_field() not in existing_indices:
            self._wfs_collection.create_index(WorkflowObject.workflow_id_field(), unique=True)

        # Creating objects collection indices:
        existing_indices = [list(x["key"].keys())[0] for x in self._obj_collection.list_indexes()]

        if "object_id" not in existing_indices:
            self._obj_collection.create_index("object_id", unique=True)

        if WorkflowObject.workflow_id_field() not in existing_indices:
            self._obj_collection.create_index(WorkflowObject.workflow_id_field(), unique=False)
        if TaskObject.task_id_field() not in existing_indices:
            self._obj_collection.create_index(TaskObject.task_id_field(), unique=False)

    def _pipeline(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
    ):
        """
        Generate a MongoDB aggregation pipeline.

        Parameters
        ----------
            filter (Dict): Match filter for the `$match` stage.
            projection (List[str]): Fields to project in the `$project` stage.
            limit (int): Maximum number of documents to return.
            sort (List[Tuple[str, int]]): Fields and orders for `$sort`.
            aggregation (List[Tuple[str, str]]): Aggregation operations and fields for `$group`.

        Returns
        -------
            List[Dict]: The result of the pipeline execution.
        """
        if projection is not None and len(projection) > 1:
            raise Exception(
                "Sorry, this query API is still limited to at most one "
                "grouping  at a time. Please use only one field in the "
                "projection argument. If you really need more than one, "
                "please contact the development team or query MongoDB "
                "directly."
            )

        pipeline = []
        # Match stage
        if filter is not None:
            pipeline.append({"$match": filter})

        projected_fields = {}
        group_id_field = None
        # Aggregation stages
        if aggregation is not None:
            if projection is not None:
                # Only one is supported now
                group_id_field = f"${projection[0]}"

            stage = {"$group": {"_id": group_id_field}}
            for operator, field in aggregation:
                fn = field.replace(".", "_")
                fn = f"{operator}_{fn}"
                field_agg = {fn: {f"${operator}": f"${field}"}}
                if projection is not None:
                    projected_fields[fn] = 1
                stage["$group"].update(field_agg)

            pipeline.append(stage)

        # Sort stage
        if sort is not None:
            sort_stage = {}
            for field, order in sort:
                sort_stage[field] = order
            pipeline.append({"$sort": sort_stage})

        # Limit stage
        if limit > 0:
            pipeline.append({"$limit": limit})

        # Projection stage
        if projection is not None:
            projected_fields.update(
                {
                    "_id": 0,
                    projection[0].replace(".", "_"): "$_id",
                }
            )
            pipeline.append({"$project": projected_fields})

        try:
            _rs = self._tasks_collection.aggregate(pipeline)
            return _rs
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_one_task(self, task_dict: Dict) -> ObjectId:
        """
        Insert a single task document into the tasks collection.

        Parameters
        ----------
        task_dict : dict
            The task data to be inserted into the tasks collection.

        Returns
        -------
        ObjectId
            The ObjectId of the inserted task document.

        Raises
        ------
        Exception
            If an error occurs during the insertion.
        """
        try:
            r = self._tasks_collection.insert_one(task_dict)
            return r.inserted_id
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_and_update_many_tasks(self, doc_list: List[Dict], indexing_key=None) -> bool:
        """
        Insert and update multiple task documents in the tasks collection.

        This method will curate the provided list of task dictionaries, update existing records
        with the same indexing key or insert new ones.

        Parameters
        ----------
        doc_list : list of dict
            The list of task data to be inserted or updated.
        indexing_key : str
            The key used to index the task documents for upsert operations.

        Returns
        -------
        bool
            True if the operation was successful, False otherwise.

        Raises
        ------
        Exception
            If an error occurs during the bulk insert or update operation.
        """
        try:
            if len(doc_list) == 0:
                return False
            if indexing_key is None:
                raise Exception("To use this method in MongoDB, please provide the indexing key.")
            t0 = 0
            if PERF_LOG:
                t0 = time()
            indexed_buffer = curate_dict_task_messages(doc_list, indexing_key, t0)
            t1 = perf_log("doc_curate_dict_task_messages", t0)
            if len(indexed_buffer) == 0:
                return False
            requests = []
            for indexing_key_value in indexed_buffer:
                requests.append(
                    UpdateOne(
                        filter={indexing_key: indexing_key_value},
                        update=[{"$set": indexed_buffer[indexing_key_value]}],
                        upsert=True,
                    )
                )
            t2 = perf_log("indexing_buffer", t1)
            self._tasks_collection.bulk_write(requests)
            perf_log("bulk_write", t2)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_task_ids(self, ids_list: List[ObjectId]) -> bool:
        """
        Delete task documents by their ObjectIds from the tasks collection.

        Parameters
        ----------
        ids_list : list of ObjectId
            The list of ObjectIds of tasks to be deleted.

        Returns
        -------
        bool
            True if the deletion was successful, False otherwise.

        Raises
        ------
        Exception
            If an error occurs during the deletion operation.
        """
        if type(ids_list) is not list:
            ids_list = [ids_list]
        try:
            self._tasks_collection.delete_many({"_id": {"$in": ids_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_task_keys(self, key_name, keys_list: List[Any]) -> bool:
        """
        Delete task documents based on a specific key and value from the tasks collection.

        Parameters
        ----------
        key_name : str
            The name of the key to be matched for deletion.
        keys_list : list of any
            The list of values for the specified key to delete the matching documents.

        Returns
        -------
        bool
            True if the deletion was successful, False otherwise.

        Raises
        ------
        Exception
            If an error occurs during the deletion operation.
        """
        if type(keys_list) is not list:
            keys_list = [keys_list]
        try:
            self._tasks_collection.delete_many({key_name: {"$in": keys_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_tasks_with_filter(self, filter) -> bool:
        """
        Delete task documents that match the specified filter.

        Parameters
        ----------
        filter : dict
            The filter criteria to match the task documents for deletion.

        Returns
        -------
        bool
            True if the deletion was successful, False otherwise.

        Raises
        ------
        Exception
            If an error occurs during the deletion operation.
        """
        try:
            self._tasks_collection.delete_many(filter)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def count_tasks(self) -> int:
        """Count number of docs in tasks collection."""
        try:
            return self._tasks_collection.count_documents({})
        except Exception as e:
            self.logger.exception(e)
            return -1

    def insert_or_update_workflow(self, workflow_obj: WorkflowObject) -> bool:
        """Insert or update workflow."""
        _dict = workflow_obj.to_dict().copy()
        workflow_id = _dict.pop(WorkflowObject.workflow_id_field(), None)
        if workflow_id is None:
            self.logger.exception("The workflow identifier cannot be none.")
            return False
        _filter = {WorkflowObject.workflow_id_field(): workflow_id}
        update_query = {}
        interceptor_ids = _dict.pop("interceptor_ids", None)
        if interceptor_ids is not None and len(interceptor_ids):
            # if not isinstance(interceptor_id, str):
            #     self.logger.exception(
            #         "Interceptor_ID must be a string, as Mongo can only record string keys."
            #     )
            #     return False
            update_query.update({"$push": {"interceptor_ids": {"$each": interceptor_ids}}})

        machine_info = _dict.pop("machine_info", None)
        if machine_info is not None:
            for k in machine_info:
                _dict[f"machine_info.{k}"] = machine_info[k]

        # TODO: for dictionary fields, like custom_metadata especially,
        #  test if we are updating or replacing when
        #  an existing wf already has custom_metadata and we call this method

        update_query.update(
            {
                "$set": _dict,
            }
        )

        try:
            result = self._wfs_collection.update_one(_filter, update_query, upsert=True)
            return (result.upserted_id is not None) or result.raw_result["updatedExisting"]
        except Exception as e:
            self.logger.exception(e)
            return False

    def to_df(self, collection="tasks", filter=None) -> pd.DataFrame:
        """
        Convert the contents of a MongoDB collection to a pandas DataFrame.

        Parameters
        ----------
        collection : str, optional
            The name of the MongoDB collection to convert to a DataFrame. Defaults to "tasks".
        filter : dict, optional
            The filter criteria to apply when retrieving the documents. Defaults to None.

        Returns
        -------
        pd.DataFrame
            A pandas DataFrame containing the documents from the specified collection.

        Raises
        ------
        Exception
            If an error occurs during the DataFrame conversion or query.
        """
        if collection == "tasks":
            _collection = self._tasks_collection
        elif collection == "workflows":
            _collection = self._wfs_collection
        else:
            msg = "Only tasks and workflows "
            raise Exception(msg + "collections are currently available for this.")
        try:
            cursor = _collection.find(filter=filter)
            return pd.DataFrame(cursor)
        except Exception as e:
            self.logger.exception(e)

    def dump_to_file(
        self,
        collection_name="tasks",
        filter=None,
        output_file=None,
        export_format="json",
        should_zip=False,
    ):
        """Dump it to file."""
        if collection_name == "tasks":
            _collection = self._tasks_collection
        elif collection_name == "workflows":
            _collection = self._wfs_collection
        else:
            msg = "Only tasks and workflows "
            raise Exception(msg + "collections are currently available for dump.")

        if export_format != "json":
            raise Exception("Sorry, only JSON is currently supported.")

        if output_file is None:
            output_file = f"docs_dump_{collection_name}_{get_utc_now_str()}"
            output_file += ".zip" if should_zip else ".json"

        try:
            cursor = _collection.find(filter=filter)
        except Exception as e:
            self.logger.exception(e)
            return

        try:
            json_data = dumps(cursor)
        except Exception as e:
            self.logger.exception(e)
            return

        try:
            if should_zip:
                in_memory_stream = io.BytesIO()
                with zipfile.ZipFile(in_memory_stream, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    zip_file.writestr("dump_file.json", json_data)
                compressed_data = in_memory_stream.getvalue()
                with open(output_file, "wb") as f:
                    f.write(compressed_data)
            else:
                with open(output_file, "w") as f:
                    json.dump(json.loads(json_data), f)

            self.logger.info(f"DB dump file {output_file} saved.")
        except Exception as e:
            self.logger.exception(e)
            return

    def liveness_test(self) -> bool:
        """Test for livelyness."""
        try:
            self._db.list_collection_names()
            return True
        except ConnectionError as e:
            self.logger.exception(e)
            return False
        except Exception as e:
            self.logger.exception(e)
            return False

    def save_object(
        self,
        object,
        object_id=None,
        task_id=None,
        workflow_id=None,
        type=None,
        custom_metadata=None,
        save_data_in_collection=False,
        pickle_=False,
    ):
        """Save an object."""
        if object_id is None:
            object_id = str(uuid4())
        obj_doc = {"object_id": object_id}

        if save_data_in_collection:
            blob = object
            if pickle_:
                blob = pickle.dumps(object)
                obj_doc["pickle"] = True
            obj_doc["data"] = blob

        else:
            from gridfs import GridFS

            fs = GridFS(self._db)
            grid_fs_file_id = fs.put(object)
            obj_doc["grid_fs_file_id"] = grid_fs_file_id

        if task_id is not None:
            obj_doc["task_id"] = task_id
        if workflow_id is not None:
            obj_doc["workflow_id"] = workflow_id
        if type is not None:
            obj_doc["type"] = type
        if custom_metadata is not None:
            obj_doc["custom_metadata"] = custom_metadata

        self._obj_collection.insert_one(obj_doc)

        return object_id

    def get_file_data(self, file_id):
        """Get a file in the GridFS."""
        from gridfs import GridFS, NoFile

        fs = GridFS(self._db)
        try:
            file_data = fs.get(file_id)
            return file_data.read()
        except NoFile:
            self.logger.error(f"File with ID {file_id} not found.")
            return None
        except Exception as e:
            self.logger.exception(f"An error occurred: {e}")
            return None

    def query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
        collection="tasks",
    ):
        """Query o MongoDB collection with optional filters, projections, sorting, and aggregation.

        Parameters
        ----------
        filter : dict, optional
            The filter criteria to match documents. Defaults to None.
        projection : list of str, optional
            The fields to include in the results. Defaults to None.
        limit : int, optional
            The maximum number of documents to return. Defaults to None (no limit).
        sort : list of tuples, optional
            The fields and order to sort the results by. Defaults to None.
        aggregation : list of tuples, optional
            The aggregation operators and fields to apply. Defaults to None.
        remove_json_unserializables : bool, optional
            If True, removes fields that are not JSON serializable. Defaults to None.
        collection : str, optional
            The name of the collection to query. Defaults to "tasks".

        Returns
        -------
        list
            A list of documents matching the query criteria.

        Raises
        ------
        Exception
            If an error occurs during the query operation.
        """
        if collection == "tasks":
            return self.task_query(
                filter,
                projection,
                limit,
                sort,
                aggregation,
                remove_json_unserializables,
            )
        elif collection == "workflows":
            return self.workflow_query(filter, projection, limit, sort, remove_json_unserializables)
        elif collection == "objects":
            return self.object_query(filter)
        else:
            raise Exception(
                f"You used type={collection}, but MongoDB only stores tasks, workflows, and objects"
            )

    def task_query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """Generate a mongo query pipeline.

        Generates a MongoDB query pipeline based on the provided arguments.

        Parameters
        ----------
        filter (dict):
            The filter criteria for the $match stage.
        projection (list, optional):
            List of fields to include in the $project stage. Defaults to None.
        limit (int, optional):
            The maximum number of documents to return. Defaults to 0 (no limit).
        sort (list of tuples, optional):
            List of (field, order) tuples specifying the sorting order. Defaults to None.
        aggregation (list of tuples, optional):
            List of (aggregation_operator, field_name) tuples specifying
            additional aggregation operations. Defaults to None.
        remove_json_unserializables:
            Removes fields that are not JSON serializable. Defaults to True

        Returns
        -------
        list:
            A list with the result set.

        Example
        -------
        Create a pipeline with a filter, projection, sorting, and aggregation.

        rs = find(
            filter={"campaign_id": "mycampaign1"},
            projection=["workflow_id", "started_at", "ended_at"],
            limit=10,
            sort=[("workflow_id", ASC), ("end_time", DESC)],
            aggregation=[("avg", "ended_at"), ("min", "started_at")]
        )
        """
        if aggregation is not None:
            try:
                rs = self._pipeline(filter, projection, limit, sort, aggregation)
            except Exception as e:
                self.logger.exception(e)
                return None
        else:
            _projection = {}
            if projection is not None:
                for proj_field in projection:
                    _projection[proj_field] = 1

            if remove_json_unserializables:
                _projection.update({"_id": 0, "timestamp": 0})
            try:
                rs = self._tasks_collection.find(
                    filter=filter,
                    projection=_projection,
                    limit=limit,
                    sort=sort,
                )
            except Exception as e:
                self.logger.exception(e)
                return None
        try:
            lst = list(rs)
            return lst
        except Exception as e:
            self.logger.exception(e)
            return None

    def workflow_query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """Get the workflow query."""
        # TODO refactor: reuse code for task_query instead of copy & paste
        _projection = {}
        if projection is not None:
            for proj_field in projection:
                _projection[proj_field] = 1

        if remove_json_unserializables:
            _projection.update({"_id": 0, "timestamp": 0})
        try:
            rs = self._wfs_collection.find(
                filter=filter,
                projection=_projection,
                limit=limit,
                sort=sort,
            )
            lst = list(rs)
            return lst
        except Exception as e:
            self.logger.exception(e)
            return None

    def object_query(self, filter) -> List[dict]:
        """Get objects."""
        try:
            documents = self._obj_collection.find(filter)
            return list(documents)
        except Exception as e:
            self.logger.exception(e)
            return None

    def close(self):
        """Close Mongo client."""
        if getattr(self, "_initialized"):
            super().close()
            setattr(self, "_initialized", False)
            self._client.close()