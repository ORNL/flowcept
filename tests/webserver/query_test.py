import unittest
import json
from threading import Thread
import requests
from time import sleep
from uuid import uuid4
from flowcept.configs import WEBSERVER_PORT, WEBSERVER_HOST
from flowcept.flowcept_webserver.app import app, BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import DocQuery

from flowcept.commons.doc_db.document_db_dao import DocumentDBDao


class QueryTest(unittest.TestCase):
    HOST = WEBSERVER_HOST
    PORT = WEBSERVER_PORT + 1
    URL = f"http://{HOST}:{PORT}{BASE_ROUTE}{DocQuery.ROUTE}"

    def __init__(self, *args, **kwargs):
        super(QueryTest, self).__init__(*args, **kwargs)
        Thread(
            target=app.run,
            kwargs={"host": QueryTest.HOST, "port": QueryTest.PORT},
            daemon=True,
        ).start()
        sleep(2)

    def gen_some_mock_data(self, size=1):
        with open("sample_data.json") as f:
            docs = json.load(f)

        i = 0
        new_docs = []
        new_ids = []
        for doc in docs:
            if i >= size:
                break

            new_doc = doc.copy()
            new_id = str(uuid4())
            new_doc["task_id"] = new_id
            new_doc.pop("_id")
            new_docs.append(new_doc)
            new_ids.append(new_id)
            i += 1

        return new_docs, new_ids

    def test_query(self):
        _filter = {"task_id": "1234"}
        request_data = {"filter": json.dumps(_filter)}

        r = requests.post(QueryTest.URL, json=request_data)
        assert r.status_code == 404

        docs, ids = self.gen_some_mock_data(size=1)

        dao = DocumentDBDao()
        c0 = dao.count()
        dao.insert_many(docs)

        _filter = {"task_id": ids[0]}
        request_data = {"filter": json.dumps(_filter)}
        r = requests.post(QueryTest.URL, json=request_data)
        assert r.status_code == 201
        assert docs[0]["task_id"] == r.json()[0]["task_id"]
        dao.delete_keys("task_id", docs[0]["task_id"])
        c1 = dao.count()
        assert c0 == c1
