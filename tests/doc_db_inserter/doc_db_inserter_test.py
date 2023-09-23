import unittest
from uuid import uuid4

from flowcept.commons.daos.document_db_dao import DocumentDBDao


class TestDocDBInserter(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(TestDocDBInserter, self).__init__(*args, **kwargs)
        self.doc_dao = DocumentDBDao()

    def test_db(self):
        c0 = self.doc_dao.count()
        assert c0 >= 0
        _id = self.doc_dao.insert_one({"dummy": "test"})
        assert _id is not None
        _ids = self.doc_dao.insert_many(
            [
                {"dummy1": "test1"},
                {"dummy2": "test2"},
            ]
        )
        assert len(_ids) == 2
        self.doc_dao.delete_ids([_id])
        self.doc_dao.delete_ids(_ids)
        c1 = self.doc_dao.count()
        assert c0 == c1

    def test_db_insert_and_update_many(self):
        c0 = self.doc_dao.count()
        assert c0 >= 0
        uid = str(uuid4())
        docs = [
            {
                "myid": uid,
                "debug": True,
                "last_name": "Souza",
                "end_time": 4,
                "status": "FINISHED",
                "used": {"any": 1},
            },
            {
                "myid": uid,
                "debug": True,
                "name": "Renan",
                "status": "SUBMITTED",
            },
            {
                "myid": uid,
                "debug": True,
                "name": "Renan2",
                "empty_string": "",
                "used": {"bla": 2, "lala": False},
            },
        ]
        self.doc_dao.insert_and_update_many("myid", docs)
        docs = [
            {
                "myid": uid,
                "debug": True,
                "name": "Renan2",
                "used": {"blub": 3},
            },
            {
                "myid": uid,
                "debug": True,
                "name": "Francisco",
                "start_time": 2,
                "status": "RUNNING",
            },
        ]
        self.doc_dao.insert_and_update_many("myid", docs)
        print(uid)
        self.doc_dao.delete_keys("myid", [uid])
        c1 = self.doc_dao.count()
        assert c0 == c1

    def test_status_updates(self):
        c0 = self.doc_dao.count()
        assert c0 >= 0
        uid = str(uuid4())
        docs = [
            {"myid": uid, "debug": True, "status": "SUBMITTED"},
            {"myid": uid, "debug": True, "status": "RUNNING"},
        ]
        self.doc_dao.insert_and_update_many("myid", docs)
        docs = [{"myid": uid, "debug": True, "status": "FINISHED"}]
        self.doc_dao.insert_and_update_many("myid", docs)
        self.doc_dao.delete_keys("myid", [uid])
        c1 = self.doc_dao.count()
        assert c0 == c1
