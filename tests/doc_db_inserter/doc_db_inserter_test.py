import unittest
from uuid import uuid4


from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
from flowcept.configs import MONGO_ENABLED


@unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
class TestMongoDBInserter(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestMongoDBInserter, self).__init__(*args, **kwargs)

    def setUp(self):
        if MONGO_ENABLED:
            self.doc_dao = MongoDBDAO(create_indices=False)
        else:
            self.doc_dao = None

    def test_db_insert_and_update_many(self):
        c0 = self.doc_dao.count_tasks()
        assert c0 >= 0
        uid = str(uuid4())
        docs = [
            {
                "task_id": str(uuid4()),
                "myid": uid,
                "debug": True,
                "last_name": "Souza",
                "end_time": 4,
                "status": "FINISHED",
                "used": {"any": 1},
            },
            {
                "task_id": str(uuid4()),
                "myid": uid,
                "debug": True,
                "name": "Renan",
                "status": "SUBMITTED",
            },
            {
                "task_id": str(uuid4()),
                "myid": uid,
                "debug": True,
                "name": "Renan2",
                "empty_string": "",
                "used": {"bla": 2, "lala": False},
            },
        ]
        self.doc_dao.insert_and_update_many_tasks(docs, "myid")
        docs = [
            {
                "task_id": str(uuid4()),
                "myid": uid,
                "debug": True,
                "name": "Renan2",
                "used": {"blub": 3},
            },
            {
                "task_id": str(uuid4()),
                "myid": uid,
                "debug": True,
                "name": "Francisco",
                "start_time": 2,
                "status": "RUNNING",
            },
        ]
        self.doc_dao.insert_and_update_many_tasks(docs, "myid")
        print(uid)
        self.doc_dao.delete_task_keys("myid", [uid])
        c1 = self.doc_dao.count_tasks()
        assert c0 == c1

    def test_status_updates(self):
        c0 = self.doc_dao.count_tasks()
        assert c0 >= 0
        uid = str(uuid4())
        docs = [
            {
                "myid": uid,
                "debug": True,
                "status": "SUBMITTED",
                "task_id": str(uuid4()),
            },
            {
                "myid": uid,
                "debug": True,
                "status": "RUNNING",
                "task_id": str(uuid4()),
            },
        ]
        self.doc_dao.insert_and_update_many_tasks(docs, "myid")
        docs = [
            {
                "myid": uid,
                "debug": True,
                "status": "FINISHED",
                "task_id": str(uuid4()),
            }
        ]
        self.doc_dao.insert_and_update_many_tasks(docs, "myid")
        self.doc_dao.delete_task_keys("myid", [uid])
        c1 = self.doc_dao.count_tasks()
        assert c0 == c1
