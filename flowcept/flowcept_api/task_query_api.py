import json
from typing import List, Dict

import requests

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import WEBSERVER_HOST, WEBSERVER_PORT
from flowcept.flowcept_webserver.app import BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery


class TaskQueryAPI(object):
    def __init__(
        self,
        host: str = WEBSERVER_HOST,
        port: int = WEBSERVER_PORT,
        auth=None,
    ):
        self.logger = FlowceptLogger().get_logger()
        self._host = host
        self._port = port
        _base_url = f"http://{self._host}:{self._port}"
        self._url = f"{_base_url}{BASE_ROUTE}{TaskQuery.ROUTE}"
        try:
            r = requests.get(_base_url)
            if r.status_code > 300:
                raise Exception(r.text)
            self.logger.debug("Ok, webserver is ready to receive requests.")
        except Exception as e:
            raise Exception(
                f"Error when accessing the webserver at {_base_url}"
            )

    def query(
        self,
        filter: dict,
        projection: dict = None,
        limit: int = 0,
        sort: dict = None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        request_data = {"filter": json.dumps(filter)}
        if projection:
            request_data["projection"] = json.dumps(projection)
        if limit:
            request_data["limit"] = limit
        if sort:
            request_data["sort"] = json.dumps(sort)
        if remove_json_unserializables:
            request_data[
                "remove_json_unserializables"
            ] = remove_json_unserializables

        r = requests.post(self._url, json=request_data)
        if 200 <= r.status_code < 300:
            return r.json()
        else:
            raise Exception(r.text)
