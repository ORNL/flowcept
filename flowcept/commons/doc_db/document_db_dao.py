from typing import List, Dict
from bson import ObjectId
from pymongo import MongoClient, UpdateOne

from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_COLLECTION,
)

from flowcept.flowcept_consumer.consumer_utils import (
    curate_dict_task_messages,
)


class DocumentDBDao(object):
    def __init__(self):
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        self._collection = db[MONGO_COLLECTION]

    def find(self, filter_: Dict) -> List[Dict]:
        try:
            lst = list()
            for doc in self._collection.find(filter_):
                lst.append(doc)
            return lst
        except Exception as e:
            print("Error when querying", e)
            return None

    def insert_one(self, doc: Dict) -> ObjectId:
        try:
            r = self._collection.insert_one(doc)
            return r.inserted_id
        except Exception as e:
            print("Error when inserting", doc, e)
            return None

    def insert_many(self, doc_list: List[Dict]) -> List[ObjectId]:
        try:
            r = self._collection.insert_many(doc_list)
            return r.inserted_ids
        except Exception as e:
            print("Error when inserting many docs", e, str(doc_list))
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
            print("Error when updating or inserting docs", e, str(doc_list))
            return False

    def delete_ids(self, ids_list: List[ObjectId]):
        try:
            self._collection.delete_many({"_id": {"$in": ids_list}})
        except Exception as e:
            print("Error when deleting documents.", e)

    def delete_keys(self, key_name, keys_list: List[ObjectId]):
        try:
            self._collection.delete_many({key_name: {"$in": keys_list}})
        except Exception as e:
            print("Error when deleting documents.", e)

    def count(self) -> int:
        try:
            return self._collection.count_documents({})
        except Exception as e:
            print("Error when counting documents.", e)
            return -1
