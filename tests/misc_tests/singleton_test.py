import unittest

from flowcept import Flowcept
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO
from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import MONGO_ENABLED
from flowcept.flowcept_api.db_api import DBAPI


class TestSingleton(unittest.TestCase):
    def test_singleton(self):
        logger = FlowceptLogger()
        try:
            dao_err = DocumentDBDAO()
        except Exception as e:
            logger.debug("This exception is expected because we can't instantiate this: " + str(e))

        dao = DocumentDBDAO.get_instance(create_indices=False)
        if dao.__class__ == MongoDBDAO:
            dao2 = MongoDBDAO()
        elif dao.__class__ == LMDBDAO:
            dao2 = LMDBDAO()
        else:
            raise NotImplementedError

        # TODO: Classes are equal but instances are not necessarily equal.
        assert id(dao) != id(dao2)
        #assert Flowcept.db._dao == dao
        #assert id(Flowcept.db._dao) == id(dao)

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_mongo_dao_singleton(self):
        doc_dao1 = MongoDBDAO()
        doc_dao2 = MongoDBDAO()
        # TODO: revise this test
        assert doc_dao1 != doc_dao2
