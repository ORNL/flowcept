import os.path
import pathlib
import unittest
import json
import random
from threading import Thread

import requests
import inspect
from time import sleep
from uuid import uuid4
from datetime import datetime, timedelta

from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import WEBSERVER_PORT, WEBSERVER_HOST, MONGO_ENABLED
from flowcept.flowcept_api.task_query_api import TaskQueryAPI
from flowcept.flowcept_webserver.app import app, BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery
from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO
from flowcept.analytics.analytics_utils import (
    clean_dataframe,
    analyze_correlations_used_vs_generated,
    analyze_correlations,
    analyze_correlations_used_vs_telemetry_diff,
    analyze_correlations_generated_vs_telemetry_diff,
    analyze_correlations_between,
)


def gen_mock_multi_workflow_data(size=1):
    """
    Generates a multi-workflow composed of two workflows.
    :param size: Maximum number of tasks to generate. The actual maximum will be 2*size because this mock data has two workflows.
    :return:
    """
    new_docs = []
    new_task_ids = []

    _end = datetime.now()

    for i in range(0, size):
        t1 = TaskObject()
        t1.task_id = str(uuid4())
        t1.workflow_name = "generate_hyperparams"
        t1.workflow_id = t1.workflow_name + str(uuid4())
        t1.adapter_id = "adapter1"
        t1.used = {"ifile": "/path/a.dat", "x": random.randint(1, 100)}
        t1.activity_id = "generate"
        t1.generated = {
            "epochs": random.randint(1, 100),
            "batch_size": random.randint(16, 20),
        }

        _start = _end + timedelta(minutes=i)
        _end = _start + timedelta(minutes=i + 1)

        t1.started_at = int(_start.timestamp())
        t1.ended_at = int(_end.timestamp())
        t1.campaign_id = "mock_campaign"
        t1.status = Status.FINISHED
        t1.user = "user_test"
        new_docs.append(t1.to_dict())
        new_task_ids.append(t1.task_id)

        t2 = TaskObject()
        t2.task_id = str(uuid4())
        t1.adapter_id = "adapter2"
        t2.workflow_name = "train"
        t2.activity_id = "fit"
        t2.workflow_id = t2.workflow_name + str(uuid4())
        t2.used = t1.generated
        t2.generated = {
            "loss": random.uniform(0.5, 50),
            "accuracy": random.uniform(0.5, 0.95),
        }

        _start = _end + timedelta(minutes=i)
        _end = _start + timedelta(minutes=i + 1)

        t2.started_at = int(_start.timestamp())
        t2.ended_at = int(_end.timestamp())
        t2.status = Status.FINISHED
        t2.campaign_id = t1.campaign_id
        t2.user = t1.campaign_id
        new_docs.append(t2.to_dict())
        new_task_ids.append(t2.task_id)

    return new_docs, new_task_ids


def gen_mock_data(size=1, with_telemetry=False):
    if with_telemetry:
        fname = "sample_data_with_telemetry_and_rai.json"
    else:
        fname = "sample_data.json"

    fpath = os.path.join(pathlib.Path(__file__).parent.resolve(), fname)
    with open(fpath) as f:
        docs = json.load(f)

    i = 0
    new_docs = []
    new_task_ids = []
    _end = datetime.now()
    for doc in docs:
        if i >= size:
            break

        new_doc = doc.copy()
        new_id = str(uuid4())
        new_doc["task_id"] = new_id

        _start = _end + timedelta(minutes=i)
        _end = _start + timedelta(minutes=i + 1)

        new_doc["started_at"] = int(_start.timestamp())
        new_doc["ended_at"] = int(_end.timestamp())
        new_doc.pop("timestamp", None)
        new_doc.pop("_id")
        new_docs.append(new_doc)
        new_task_ids.append(new_id)
        i += 1

    return new_docs, new_task_ids


@unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
class TaskQueryAPITest(unittest.TestCase):
    URL = f"http://{WEBSERVER_HOST}:{WEBSERVER_PORT}{BASE_ROUTE}{TaskQuery.ROUTE}"

    @classmethod
    def setUpClass(cls):
        Thread(
            target=app.run,
            kwargs={"host": WEBSERVER_HOST, "port": WEBSERVER_PORT},
            daemon=True,
        ).start()
        sleep(2)

    def __init__(self, *args, **kwargs):
        super(TaskQueryAPITest, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()
        self.api = TaskQueryAPI()

    def gen_n_get_task_ids(self, generation_function, size=1, generation_args={}):
        docs, task_ids = generation_function(size=size, **generation_args)

        dao = DocumentDBDAO.get_instance(create_indices=False)
        init_db_count = dao.count_tasks()
        dao.insert_and_update_many_tasks(docs, "task_id")

        task_ids_filter = {"task_id": {"$in": task_ids}}
        return task_ids_filter, task_ids, init_db_count

    def delete_task_ids_and_assert(self, task_ids, init_db_count):
        dao = DocumentDBDAO.get_instance(create_indices=False)
        dao.delete_task_keys("task_id", task_ids)
        final_db_count = dao.count_tasks()
        assert init_db_count == final_db_count

    def test_webserver_query(self):
        _filter = {"task_id": "1234"}
        request_data = {"filter": json.dumps(_filter)}

        r = requests.post(TaskQueryAPITest.URL, json=request_data)
        assert r.status_code == 404

        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(gen_mock_data, size=1)
        request_data = {"filter": json.dumps(task_ids_filter)}
        r = requests.post(TaskQueryAPITest.URL, json=request_data)
        assert r.status_code == 201
        assert len(r.json()) == len(task_ids)
        assert task_ids[0] == r.json()[0]["task_id"]
        self.delete_task_ids_and_assert(task_ids, init_db_count)

    def test_query_api_with_webserver(self):
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(gen_mock_data, size=1)
        api = TaskQueryAPI(with_webserver=True)
        r = api.query(task_ids_filter)
        assert len(r) > 0
        assert task_ids[0] == r[0]["task_id"]
        self.delete_task_ids_and_assert(task_ids, init_db_count)

    @unittest.skip("This is testing a deprecated feature.")
    def test_query_api_with_and_without_webserver(self):
        query_api_params = inspect.signature(TaskQueryAPI.query).parameters
        doc_query_api_params = inspect.signature(MongoDBDAO.task_query).parameters
        assert query_api_params == doc_query_api_params, "Function signatures do not match."

        query_api_docstring = inspect.getdoc(TaskQueryAPI.query)
        doc_query_api_docstring = inspect.getdoc(MongoDBDAO.task_query)

        assert (
            query_api_docstring.strip() == doc_query_api_docstring.strip()
        ), "The docstrings are not equal."

        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(gen_mock_data, size=1)

        api_without = TaskQueryAPI(with_webserver=False)
        res_without = api_without.query(task_ids_filter)
        assert len(res_without) > 0
        assert task_ids[0] == res_without[0]["task_id"]

        api_with = TaskQueryAPI(with_webserver=True)
        res_with = api_with.query(task_ids_filter)
        assert len(res_with) > 0
        assert task_ids[0] == res_without[0]["task_id"]

        assert res_without == res_with

        self.delete_task_ids_and_assert(task_ids, init_db_count)

    def test_aggregation(self):
        docs, task_ids = gen_mock_multi_workflow_data(size=100)

        dao = MongoDBDAO()
        c0 = dao.count_tasks()
        dao.insert_and_update_many_tasks(docs, indexing_key="task_id")
        res = self.api.query(
            aggregation=[
                ("max", "used.epochs"),
                ("max", "generated.accuracy"),
                ("avg", "used.batch_size"),
            ]
        )
        assert len(res) > 0
        for doc in res:
            if doc.get("max_generated_accuracy") is not None:
                assert doc["max_generated_accuracy"] > 0

        campaign_id = docs[0]["campaign_id"]
        res = self.api.query(
            filter={"campaign_id": campaign_id},
            aggregation=[
                ("max", "used.epochs"),
                ("max", "generated.accuracy"),
                ("avg", "used.batch_size"),
            ],
            sort=[
                ("max_used_epochs", TaskQueryAPI.ASC),
                ("ended_at", TaskQueryAPI.DESC),
            ],
            limit=10,
        )
        assert len(res) > 0
        for doc in res:
            if doc.get("max_generated_accuracy") is not None:
                assert doc["max_generated_accuracy"] > 0

        res = self.api.query(
            projection=["used.batch_size"],
            filter={"campaign_id": campaign_id},
            aggregation=[
                ("min", "generated.loss"),
                ("max", "generated.accuracy"),
            ],
            sort=[
                ("ended_at", TaskQueryAPI.DESC),
            ],
            limit=10,
        )
        assert len(res) > 1
        for doc in res:
            if doc.get("max_generated_accuracy") is not None:
                assert doc["max_generated_accuracy"] > 0

        dao.delete_task_keys("task_id", task_ids)
        c1 = dao.count_tasks()
        assert c0 == c1

    def test_query_df(self):
        max_docs = 5
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data, size=max_docs
        )
        res = self.api.df_query(task_ids_filter, remove_json_unserializables=False)
        assert len(res) == max_docs
        self.delete_task_ids_and_assert(task_ids, init_db_count)

    def test_query_df_telemetry(self):
        max_docs = 5
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
            generation_args={"with_telemetry": True},
        )
        df = self.api.df_query(
            task_ids_filter,
            remove_json_unserializables=False,
            calculate_telemetry_diff=True,
        )
        self.delete_task_ids_and_assert(task_ids, init_db_count)
        assert len(df) == max_docs
        cleaned_df = clean_dataframe(df, aggregate_telemetry=True)
        assert len(df.columns) > len(cleaned_df.columns)

    def test_df_get_top_k_tasks(self):
        max_docs = 100
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
        )
        sort = [
            ("generated.loss", TaskQueryAPI.ASC),
            ("used.batch_size", TaskQueryAPI.DESC),
        ]
        df = self.api.df_get_top_k_tasks(
            filter=task_ids_filter,
            calculate_telemetry_diff=False,
            sort=sort,
            k=10,
        )
        self.delete_task_ids_and_assert(task_ids, init_db_count)
        assert len(df) < max_docs

    def test_query_df_top_k_quantiles(self):
        max_docs = 100
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
        )
        clauses = [
            ("used.batch_size", ">=", 0.1),
            ("generated.loss", "<=", 0.9),
        ]
        sort = [
            ("used.batch_size", TaskQueryAPI.ASC),
            ("generated.loss", TaskQueryAPI.DESC),
        ]
        df = self.api.df_get_tasks_quantiles(
            clauses=clauses,
            filter=task_ids_filter,
            sort=sort,
            calculate_telemetry_diff=False,
            clean_dataframe=False,
        )
        self.delete_task_ids_and_assert(task_ids, init_db_count)
        assert 0 < len(df) < max_docs

    def test_query_df_top_k_quantiles_sorted(self):
        max_docs = 100
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
            generation_args={"with_telemetry": True},
        )
        clauses = [
            ("telemetry_diff.process.cpu_times.user", "<", 0.5),
        ]
        sort = [
            ("telemetry_diff.process.cpu_times.user", TaskQueryAPI.ASC),
            ("generated.loss", TaskQueryAPI.ASC),
            ("generated.responsible_ai_metadata.flops", TaskQueryAPI.ASC),
        ]
        df = self.api.df_get_tasks_quantiles(
            clauses=clauses,
            filter=task_ids_filter,
            sort=sort,
            calculate_telemetry_diff=True,
            clean_dataframe=True,
        )
        self.delete_task_ids_and_assert(task_ids, init_db_count)
        assert 0 < len(df) < max_docs

    def test_correlations(self):
        max_docs = 9
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
            generation_args={"with_telemetry": True},
        )
        df = self.api.df_query(task_ids_filter, calculate_telemetry_diff=True)
        self.delete_task_ids_and_assert(task_ids, init_db_count)
        assert len(df) == max_docs

        df = clean_dataframe(df, aggregate_telemetry=True, sum_lists=True)

        correlations_df = analyze_correlations(df)
        assert len(correlations_df)

        correlations_df = analyze_correlations_between(
            df, col_pattern1="generated.", col_pattern2="used."
        )
        assert len(correlations_df)

        correlations_df_ = analyze_correlations_used_vs_generated(df)
        assert len(correlations_df_)
        assert all(correlations_df == correlations_df_)

        correlations_df = analyze_correlations_used_vs_telemetry_diff(df)
        assert len(correlations_df)

        correlations_df = analyze_correlations_generated_vs_telemetry_diff(df)

        assert len(correlations_df)

    def test_find_best_tasks(self):
        max_docs = 9
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
            generation_args={"with_telemetry": True},
        )
        best_tasks = (
            self.api.find_interesting_tasks_based_on_correlations_generated_and_telemetry_data(
                filter=task_ids_filter
            )
        )
        assert len(best_tasks)
        self.delete_task_ids_and_assert(task_ids, init_db_count)

    def test_find_outliers(self):
        max_docs = 9
        task_ids_filter, task_ids, init_db_count = self.gen_n_get_task_ids(
            gen_mock_data,
            size=max_docs,
            generation_args={"with_telemetry": True},
        )
        outliers = self.api.df_find_outliers(
            outlier_threshold=5,
            calculate_telemetry_diff=True,
            filter=task_ids_filter,
            clean_dataframe=True,
            keep_task_id=True,
        )
        assert len(outliers)
        self.delete_task_ids_and_assert(task_ids, init_db_count)
