from typing import List, Dict, Optional
from bson import ObjectId
from pymongo import MongoClient, UpdateOne

from flowcept.configs import (
    MONGO_HOST,
    MONGO_PORT,
    MONGO_DB,
    MONGO_COLLECTION,
)

from flowcept.commons.flowcept_data_classes import TaskMessage, Status


def curate_task_messages(doc_list: List[Dict],
                         indexing_key: str):
    """
       This function removes duplicates based on the
        indexing_key (e.g., task_id) locally before sending
        to MongoDB.
        It also avoids tasks changing states once they go into finished state.
        This is needed because we can't guarantee MQ orders, and finished
        states have higher priority in status changes, as we don't expect a
        status change once a task goes into finished state.
        It also resolves updates (instead of replacement) of
        inner nested fields in a JSON object.
    :param doc_list:
    :param indexing_key:
    :return:
    """
    indexed_buffer = {}
    for doc in doc_list:

        if (len(doc) == 1) and (indexing_key in doc) and (doc[indexing_key] in indexed_buffer):
            # This task_msg does not add any metadata
            continue

        indexing_key_value = doc[indexing_key]
        if doc[indexing_key] not in indexed_buffer:
            indexed_buffer[indexing_key_value] = doc
            continue

        if 'finished' in indexed_buffer[indexing_key_value] and 'status' in doc:
            doc.pop('status')

        if 'status' in doc:
            for finished_status in Status.get_finished_statuses():
                if finished_status == doc['status']:
                    indexed_buffer[indexing_key_value]['finished'] = True

        for field in TaskMessage.get_dict_field_names():
            if field in doc:
                if doc[field] is not None and len(doc[field]):
                    if field in indexed_buffer[indexing_key_value]:
                        indexed_buffer[indexing_key_value][
                            field].update(doc[field])
                    else:
                        indexed_buffer[indexing_key_value][field] = \
                        doc[field]
                doc.pop(field)

        indexed_buffer[indexing_key_value].update(**doc)
    return indexed_buffer


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

    def insert_and_update_many(self, indexing_key, doc_list: List[Dict], nested_fields: Optional[List[str]] = None) -> bool:
        try:
            indexed_buffer = curate_task_messages(
                doc_list,
                indexing_key
            )
        except Exception as e:
            print("Error when updating or inserting docs", e, str(doc_list))
            return False

        requests = []
        try:
            for indexing_key_value in indexed_buffer:
                if "finished" in indexed_buffer[indexing_key_value]:
                    indexed_buffer[indexing_key_value].pop('finished')
                requests.append(UpdateOne(
                    filter={indexing_key: indexing_key_value},
                    update=[{"$set": indexed_buffer[indexing_key_value]}],
                    upsert=True))
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
