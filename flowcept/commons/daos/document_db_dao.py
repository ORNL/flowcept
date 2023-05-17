from typing import List, Dict
from bson import ObjectId
from pymongo import MongoClient, UpdateOne

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.flowcept_data_classes import TaskMessage
from flowcept.commons.utils import perf_log, get_utc_now
from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_COLLECTION,
    PERF_LOG
)
from flowcept.flowceptor.consumers.consumer_utils import (
    curate_dict_task_messages,
)
from time import time


class DocumentDBDao(object):
    def __init__(self):
        self.logger = FlowceptLogger().get_logger()
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        self._collection = db[MONGO_COLLECTION]
        self._collection.create_index(TaskMessage.get_index_field())

    def find(
        self,
        filter: dict,
        projection=None,
        limit=0,
        sort=None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        if remove_json_unserializables:
            projection = {"_id": 0, "timestamp": 0}

        try:
            lst = list()
            for doc in self._collection.find(
                filter=filter, projection=projection, limit=limit, sort=sort
            ):
                lst.append(doc)
            return lst
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_one(self, doc: Dict) -> ObjectId:
        try:
            r = self._collection.insert_one(doc)
            return r.inserted_id
        except Exception as e:
            self.logger.exception(e)
            return None

    def insert_many(self, doc_list: List[Dict]) -> List[ObjectId]:
        try:
            r = self._collection.insert_many(doc_list)
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
            self._collection.bulk_write(requests)
            perf_log("bulk_write", t2)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_ids(self, ids_list: List[ObjectId]) -> bool:
        if type(ids_list) != list:
            ids_list = [ids_list]
        try:
            self._collection.delete_many({"_id": {"$in": ids_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_keys(self, key_name, keys_list: List[ObjectId]) -> bool:
        if type(keys_list) != list:
            keys_list = [keys_list]
        try:
            self._collection.delete_many({key_name: {"$in": keys_list}})
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def count(self) -> int:
        try:
            return self._collection.count_documents({})
        except Exception as e:
            self.logger.exception(e)
            return -1
