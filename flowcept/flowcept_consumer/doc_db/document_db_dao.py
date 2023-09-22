from typing import List, Dict
from bson import ObjectId
from pymongo import MongoClient

from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_TASK_COLLECTION,
)


class DocumentDBDao(object):
    def __init__(self):
        client = MongoClient(MONGO_HOST, MONGO_PORT)
        db = client[MONGO_DB]
        self._collection = db[MONGO_TASK_COLLECTION]

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

    def delete(self, doc_list: List[ObjectId]):
        try:
            self._collection.delete_many({"_id": {"$in": doc_list}})
        except Exception as e:
            print("Error when deleting documents.", e)

    def count(self) -> int:
        try:
            return self._collection.count_documents({})
        except Exception as e:
            print("Error when counting documents.", e)
            return -1
