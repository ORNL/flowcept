from typing import List, Dict, Tuple, Any
from bson import ObjectId
from pymongo import MongoClient, UpdateOne

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.flowcept_dataclasses.task_message import TaskMessage
from flowcept.commons.utils import perf_log
from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_TASK_COLLECTION,
    MONGO_WORKFLOWS_COLLECTION,
    PERF_LOG,
)
from flowcept.flowceptor.consumers.consumer_utils import (
    curate_dict_task_messages,
)
from time import time


class DocumentDBDao(object):
    def __init__(self):
        self.logger = FlowceptLogger().get_logger()
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        self._db = client[MONGO_DB]

        self._tasks_collection = self._db[MONGO_TASK_COLLECTION]
        self._tasks_collection.create_index(TaskMessage.get_index_field())

        self._wfs_collection = self._db[MONGO_WORKFLOWS_COLLECTION]
        self._wfs_collection.create_index(TaskMessage.get_workflow_id_field())

    def task_query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """
        Generates a MongoDB query pipeline based on the provided arguments.
        Parameters:
            filter (dict): The filter criteria for the $match stage.
            projection (list, optional): List of fields to include in the $project stage. Defaults to None.
            limit (int, optional): The maximum number of documents to return. Defaults to 0 (no limit).
            sort (list of tuples, optional): List of (field, order) tuples specifying the sorting order. Defaults to None.
            aggregation (list of tuples, optional): List of (aggregation_operator, field_name) tuples
                specifying additional aggregation operations. Defaults to None.
            remove_json_unserializables: removes fields that are not JSON serializable. Defaults to True

        Returns:
            list: A list with the result set.

        Example:
            # Create a pipeline with a filter, projection, sorting, and aggregation
            rs = find(
                filter={"campaign_id": "mycampaign1"},
                projection=["workflow_id", "started_at", "ended_at"],
                limit=10,
                sort=[("workflow_id", 1), ("end_time", -1)],
                aggregation=[("avg", "ended_at"), ("min", "started_at")]
            )
        """

        if aggregation is not None:
            try:
                rs = self._pipeline(
                    filter, projection, limit, sort, aggregation
                )
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
        try:
            r = self._tasks_collection.insert_one(doc)
            return r.inserted_id
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_many(self, doc_list: List[Dict]) -> List[ObjectId]:
        try:
            r = self._tasks_collection.insert_many(doc_list)
            return r.inserted_ids
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_and_update_many(
        self, indexing_key, doc_list: List[Dict]
    ) -> bool:
        try:
            if len(doc_list) == 0:
                return False
            t0 = 0
            if PERF_LOG:
                t0 = time()
            indexed_buffer = curate_dict_task_messages(
                doc_list, indexing_key, t0
            )
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
        if type(ids_list) != list:
            ids_list = [ids_list]
        try:
            self._tasks_collection.delete_many({"_id": {"$in": ids_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_keys(self, key_name, keys_list: List[Any]) -> bool:
        if type(keys_list) != list:
            keys_list = [keys_list]
        try:
            self._tasks_collection.delete_many({key_name: {"$in": keys_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def count(self) -> int:
        try:
            return self._tasks_collection.count_documents({})
        except Exception as e:
            self.logger.exception(e)
            return -1

    def workflow_insert_or_update(
        self, workflow_id: str, _dict: Dict
    ) -> bool:
        _filter = {TaskMessage.get_workflow_id_field(): workflow_id}
        custom_metadata = _dict.get("custom_metadata")
        if custom_metadata is not None:
            _dict.pop("custom_metadata")
            data_to_update = _dict.copy()
            for k, v in custom_metadata.items():
                data_to_update[f"custom_metadata.{k}"] = v
        else:
            data_to_update = _dict.copy()
        update_query = {"$set": data_to_update}
        try:
            result = self._wfs_collection.update_one(
                _filter, update_query, upsert=True
            )
            return (result.upserted_id is not None) or result.raw_result[
                "updatedExisting"
            ]
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
