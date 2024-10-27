"""Document module."""

from typing import List, Dict, Tuple, Any
import io
import json
from uuid import uuid4

import pickle
import zipfile

from bson import ObjectId
from bson.json_util import dumps
from pymongo import MongoClient, UpdateOne

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.utils import perf_log, get_utc_now_str
from flowcept.commons import singleton
from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_TASK_COLLECTION,
    MONGO_WORKFLOWS_COLLECTION,
    PERF_LOG,
    MONGO_URI,
    MONGO_CREATE_INDEX,
)
from flowcept.flowceptor.consumers.consumer_utils import (
    curate_dict_task_messages,
)
from time import time


@singleton
class DocumentDBDao(object):
    """Document class."""

    def __init__(self, create_index=MONGO_CREATE_INDEX):
        self.logger = FlowceptLogger()

        if MONGO_URI is not None:
            client = MongoClient(MONGO_URI)
        else:
            client = MongoClient(MONGO_HOST, MONGO_PORT)
        self._db = client[MONGO_DB]

        self._tasks_collection = self._db[MONGO_TASK_COLLECTION]
        self._wfs_collection = self._db[MONGO_WORKFLOWS_COLLECTION]
        self._obj_collection = self._db["objects"]

        if create_index:
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

    def _pipeline(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
    ):
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

    def insert_one(self, doc: Dict) -> ObjectId:
        """Insert only one."""
        try:
            r = self._tasks_collection.insert_one(doc)
            return r.inserted_id
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_many(self, doc_list: List[Dict]) -> List[ObjectId]:
        """Insert many."""
        try:
            r = self._tasks_collection.insert_many(doc_list)
            return r.inserted_ids
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_and_update_many(self, indexing_key, doc_list: List[Dict]) -> bool:
        """Insert and update."""
        try:
            if len(doc_list) == 0:
                return False
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

    def delete_ids(self, ids_list: List[ObjectId]) -> bool:
        """Delete the ids."""
        if type(ids_list) is not list:
            ids_list = [ids_list]
        try:
            self._tasks_collection.delete_many({"_id": {"$in": ids_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_keys(self, key_name, keys_list: List[Any]) -> bool:
        """Delete the keys."""
        if type(keys_list) is not list:
            keys_list = [keys_list]
        try:
            self._tasks_collection.delete_many({key_name: {"$in": keys_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_with_filter(self, filter) -> bool:
        """Delete with filter."""
        try:
            self._tasks_collection.delete_many(filter)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def count(self) -> int:
        """Count it."""
        try:
            return self._tasks_collection.count_documents({})
        except Exception as e:
            self.logger.exception(e)
            return -1

    def workflow_insert_or_update(self, workflow_obj: WorkflowObject) -> bool:
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

    def dump_to_file(
        self,
        collection_name=MONGO_TASK_COLLECTION,
        filter=None,
        output_file=None,
        export_format="json",
        should_zip=False,
    ):
        """Dump it to file."""
        if collection_name == MONGO_TASK_COLLECTION:
            _collection = self._tasks_collection
        elif collection_name == MONGO_WORKFLOWS_COLLECTION:
            _collection = self._wfs_collection
        else:
            msg = f"Only {MONGO_TASK_COLLECTION} and {MONGO_WORKFLOWS_COLLECTION} "
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
        pickle_=False,
    ):
        """Save an object."""
        if object_id is None:
            object_id = str(uuid4())
        obj_doc = {"object_id": object_id}
        blob = object
        if pickle_:
            blob = pickle.dumps(object)
            obj_doc["pickle"] = True
        obj_doc["data"] = blob
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

    def get_objects(self, filter):
        """Get some objects."""
        documents = self._obj_collection.find(filter)
        return list(documents)
