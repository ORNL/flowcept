from typing import List, Dict
from bson import ObjectId
from pymongo import MongoClient, UpdateOne

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_COLLECTION,
)
from flowcept.flowceptor.consumers.consumer_utils import (
    curate_dict_task_messages,
)


class DocumentDBDao(object):
    def __init__(self):
        self.logger = FlowceptLogger().get_logger()
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        self._collection = db[MONGO_COLLECTION]

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
            indexed_buffer = curate_dict_task_messages(doc_list, indexing_key)
            requests = []
            for indexing_key_value in indexed_buffer:
                if "finished" in indexed_buffer[indexing_key_value]:
                    indexed_buffer[indexing_key_value].pop("finished")
                requests.append(
                    UpdateOne(
                        filter={indexing_key: indexing_key_value},
                        update=[{"$set": indexed_buffer[indexing_key_value]}],
                        upsert=True,
                    )
                )
            self._collection.bulk_write(requests)
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
