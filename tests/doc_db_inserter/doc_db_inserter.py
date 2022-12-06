import unittest

from flowcept.flowcept_consumer.doc_db.document_db_dao import DocumentDBDao


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
        self.doc_dao.delete([_id])
        self.doc_dao.delete(_ids)
        c1 = self.doc_dao.count()
        assert c0 == c1
