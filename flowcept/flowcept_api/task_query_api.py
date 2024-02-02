from typing import List, Dict, Tuple
from datetime import datetime, timedelta
import json

import pandas as pd
import pymongo
import requests

from bson.objectid import ObjectId

from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_dataclasses.task_message import Status
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import WEBSERVER_HOST, WEBSERVER_PORT
from flowcept.flowcept_webserver.app import BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery


class TaskQueryAPI(object):
    ASC = pymongo.ASCENDING
    DESC = pymongo.DESCENDING

    def __init__(
        self,
        with_webserver=False,
        host: str = WEBSERVER_HOST,
        port: int = WEBSERVER_PORT,
        auth=None,
    ):
        self.logger = FlowceptLogger().get_logger()
        self.with_webserver = with_webserver
        if self.with_webserver:
            self._host = host
            self._port = port
            _base_url = f"http://{self._host}:{self._port}"
            self._url = f"{_base_url}{BASE_ROUTE}{TaskQuery.ROUTE}"
            try:
                r = requests.get(_base_url)
                if r.status_code > 300:
                    raise Exception(r.text)
                self.logger.debug(
                    "Ok, webserver is ready to receive requests."
                )
            except Exception as e:
                raise Exception(
                    f"Error when accessing the webserver at {_base_url}"
                )

    def query_returning_df(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
        shift_hours: int = 0,
    ) -> pd.DataFrame:
        docs = self.query(
            filter,
            projection,
            limit,
            sort,
            aggregation,
            remove_json_unserializables,
        )
        df = self._get_dataframe_from_task_docs(docs, shift_hours)
        return df

    def query(
        self,
        filter: Dict = None,
        projection: List[str] = None,
        limit: int = 0,
        sort: List[Tuple] = None,
        aggregation: List[Tuple] = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """
        Generates a MongoDB query pipeline based on the provided arguments.
        Parameters:
            filter (dict): The filter criteria for the $match stage.
            projection (list, optional): List of fields to include in the $project stage. Defaults to None.
            limit (int, optional): The maximum number of documents to return. Defaults to 0 (no limit).
            sort (list of tuples, optional): List of (field, order) tuples specifying the sorting order. Defaults to None.
            aggregation (list of tuples, optional): List of (aggregation_operator, field_name) tuples
                specifying additional aggregation operations. Defaults to None.
            remove_json_unserializables: removes fields that are not JSON serializable. Defaults to True

        Returns:
            list: A list with the result set.

        Example:
            # Create a pipeline with a filter, projection, sorting, and aggregation
            rs = find(
                filter={"campaign_id": "mycampaign1"},
                projection=["workflow_id", "started_at", "ended_at"],
                limit=10,
                sort=[("workflow_id", 1), ("end_time", -1)],
                aggregation=[("avg", "ended_at"), ("min", "started_at")]
            )
        """

        if self.with_webserver:
            request_data = {"filter": json.dumps(filter)}
            if projection:
                request_data["projection"] = json.dumps(projection)
            if limit:
                request_data["limit"] = limit
            if sort:
                request_data["sort"] = json.dumps(sort)
            if aggregation:
                request_data["aggregation"] = json.dumps(aggregation)
            if remove_json_unserializables:
                request_data[
                    "remove_json_unserializables"
                ] = remove_json_unserializables

            r = requests.post(self._url, json=request_data)
            if 200 <= r.status_code < 300:
                return r.json()
            else:
                raise Exception(r.text)

        else:
            dao = DocumentDBDao()
            docs = dao.task_query(
                filter,
                projection,
                limit,
                sort,
                aggregation,
                remove_json_unserializables,
            )
            if docs:
                return docs
            else:
                self.logger.error("Error when executing query.")

    def _get_dataframe_from_task_docs(
        self, docs: [List[Dict]], shift_hours=0
    ) -> pd.DataFrame:
        def __get_doc_status(row):
            if row.get("status"):
                return row.get("status")
            elif row.get("finished"):
                return Status.FINISHED.name
            elif row.get("error"):
                return Status.ERROR.name
            elif row.get("running"):
                return Status.RUNNING.name
            elif row.get("submitted"):
                return Status.SUBMITTED.name
            else:
                return Status.UNKNOWN.name

        def __to_datetime(_df, column_name, _shift_hours=0):
            if column_name in _df.columns:
                try:
                    _df[column_name] = pd.to_datetime(
                        _df[column_name], unit="s"
                    ) + timedelta(hours=_shift_hours)
                except Exception as _e:
                    self.logger.exception(_e)

        try:
            df = pd.json_normalize(docs)
        except Exception as e:
            self.logger.exception(e)
            return None

        try:
            df["status"] = df.apply(__get_doc_status, axis=1)
        except Exception as e:
            self.logger.exception(e)

        try:
            df = df.drop(
                columns=["finished", "error", "running", "submitted"],
                errors="ignore",
            )
        except Exception as e:
            self.logger.exception(e)

        for col in [
            "started_at",
            "ended_at",
            "submitted_at",
            "utc_timestamp",
        ]:
            __to_datetime(df, col)

        if "_id" in df.columns:
            try:
                df["doc_generated_time"] = df["_id"].apply(
                    lambda _id: ObjectId(_id).generation_time
                    + timedelta(hours=shift_hours)
                )
            except Exception as e:
                self.logger.exception(e)

        try:
            df["elapsed_time"] = df["ended_at"] - df["started_at"]
            df["elapsed_time"] = df["elapsed_time"].apply(
                lambda x: x.total_seconds()
                if isinstance(x, timedelta)
                else -1
            )
        except Exception as e:
            self.logger.exception(e)

        return df
