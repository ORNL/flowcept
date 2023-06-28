import os.path
import pathlib
import unittest
import json
from threading import Thread
import requests
import inspect
from time import sleep
from uuid import uuid4
from flowcept.configs import WEBSERVER_PORT, WEBSERVER_HOST
from flowcept.flowcept_api.task_query_api import TaskQueryAPI
from flowcept.flowcept_webserver.app import app, BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery
from flowcept.commons.daos.document_db_dao import DocumentDBDao


def gen_some_mock_data(size=1):
    fpath = os.path.join(
        pathlib.Path(__file__).parent.resolve(), "sample_data.json"
    )
    with open(fpath) as f:
        docs = json.load(f)

    i = 0
    new_docs = []
    new_task_ids = []
    for doc in docs:
        if i >= size:
            break

        new_doc = doc.copy()
        new_id = str(uuid4())
        new_doc["task_id"] = new_id
        new_doc.pop("_id")
        new_docs.append(new_doc)
        new_task_ids.append(new_id)
        i += 1

    return new_docs, new_task_ids


class QueryTest(unittest.TestCase):
    URL = f"http://{WEBSERVER_HOST}:{WEBSERVER_PORT}{BASE_ROUTE}{TaskQuery.ROUTE}"

    @classmethod
    def setUpClass(cls):
        Thread(
            target=app.run,
            kwargs={"host": WEBSERVER_HOST, "port": WEBSERVER_PORT},
            daemon=True,
        ).start()
        sleep(2)

    def test_webserver_query(self):
        _filter = {"task_id": "1234"}
        request_data = {"filter": json.dumps(_filter)}

        r = requests.post(QueryTest.URL, json=request_data)
        assert r.status_code == 404

        docs, task_ids = gen_some_mock_data(size=1)

        dao = DocumentDBDao()
        c0 = dao.count()
        dao.insert_many(docs)

        _filter = {"task_id": task_ids[0]}
        request_data = {"filter": json.dumps(_filter)}
        r = requests.post(QueryTest.URL, json=request_data)
        assert r.status_code == 201
        assert docs[0]["task_id"] == r.json()[0]["task_id"]
        dao.delete_keys("task_id", docs[0]["task_id"])
        c1 = dao.count()
        assert c0 == c1

    def test_query_api(self):
        docs, task_ids = gen_some_mock_data(size=1)

        dao = DocumentDBDao()
        c0 = dao.count()
        dao.insert_many(docs)

        api = TaskQueryAPI(with_webserver=True)
        _filter = {"task_id": task_ids[0]}
        res = api.query(_filter)
        assert len(res) > 0
        assert docs[0]["task_id"] == res[0]["task_id"]
        dao.delete_keys("task_id", docs[0]["task_id"])
        c1 = dao.count()
        assert c0 == c1

    def test_query_without_webserver(self):
        docs, task_ids = gen_some_mock_data(size=1)

        dao = DocumentDBDao()
        c0 = dao.count()
        dao.insert_many(docs)

        api = TaskQueryAPI(with_webserver=False)
        _filter = {"task_id": task_ids[0]}
        res = api.query(_filter)
        assert len(res) > 0
        assert docs[0]["task_id"] == res[0]["task_id"]
        dao.delete_keys("task_id", docs[0]["task_id"])
        c1 = dao.count()
        assert c0 == c1

    def test_query_api_with_and_without_webserver(self):
        query_api_params = inspect.signature(TaskQueryAPI.query).parameters
        doc_query_api_params = inspect.signature(
            DocumentDBDao.query
        ).parameters
        assert (
            query_api_params == doc_query_api_params
        ), "Function signatures do not match."

        query_api_docstring = inspect.getdoc(TaskQueryAPI.query)
        doc_query_api_docstring = inspect.getdoc(DocumentDBDao.query)

        assert (
            query_api_docstring.strip() == doc_query_api_docstring.strip()
        ), "The docstrings are not equal."

        docs, task_ids = gen_some_mock_data(size=1)

        dao = DocumentDBDao()
        c0 = dao.count()
        dao.insert_many(docs)

        api_without = TaskQueryAPI(with_webserver=False)
        _filter = {"task_id": task_ids[0]}
        res_without = api_without.query(_filter)
        assert len(res_without) > 0
        assert docs[0]["task_id"] == res_without[0]["task_id"]

        api_with = TaskQueryAPI(with_webserver=True)
        res_with = api_with.query(_filter)
        assert len(res_with) > 0
        assert docs[0]["task_id"] == res_with[0]["task_id"]

        assert res_without == res_with

        dao.delete_keys("task_id", docs[0]["task_id"])
        c1 = dao.count()
        assert c0 == c1

    def test_aggregation(self):
        docs, task_ids = gen_some_mock_data(size=100)

        dao = DocumentDBDao()
        c0 = dao.count()
        dao.insert_many(docs)

        api = TaskQueryAPI()
        res = api.query(
            aggregation=[
                ("max", "used.number_epochs"),
                ("max", "generated.accuracy"),
                ("avg", "used.batch_size"),
            ]
        )
        assert len(res) > 0

        res = api.query(
            aggregation=[
                ("max", "used.number_epochs"),
                ("max", "generated.accuracy"),
                ("avg", "used.batch_size"),
            ]
        )
        assert len(res) > 0

        dao.delete_keys("task_id", task_ids)
        c1 = dao.count()
        assert c0 == c1
