from threading import Thread
from time import sleep

from flowcept.commons.doc_db.document_inserter import DocumentInserter

import json
from typing import List, Dict
import requests

from flowcept.configs import WEBSERVER_PORT, WEBSERVER_HOST
from flowcept.flowcept_webserver.app import BASE_ROUTE
from flowcept.flowcept_webserver.resources.query_rsrc import TaskQuery


class FlowceptConsumerAPI(object):
    def __init__(self):
        self._consumer_thread: Thread = None

    def start(self):
        self._consumer_thread = Thread(target=DocumentInserter().main)
        self._consumer_thread.start()
        print("Flowcept Consumer starting...")
        sleep(2)
        print("Ok, we're consuming messages!")

    # def close(self):
    #     self._consumer_thread.join()


class TaskQueryAPI(object):
    def __init__(
        self,
        host: str = WEBSERVER_HOST,
        port: int = WEBSERVER_PORT,
        auth=None,
    ):
        self._host = host
        self._port = port
        self._url = (
            f"http://{self._host}:{self._port}{BASE_ROUTE}{TaskQuery.ROUTE}"
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
