import json
from typing import List, Dict, Tuple

import pymongo
import requests

from flowcept.commons.daos.document_db_dao import DocumentDBDao
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
                self.logger.error("Exception when executing query.")
