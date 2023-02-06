import sys
import json
from time import time, sleep
from threading import Thread
from typing import Dict
from datetime import datetime

from flowcept.configs import (
    MONGO_INSERTION_BUFFER_TIME,
    MONGO_INSERTION_BUFFER_SIZE,
    DEBUG_MODE,
)
from flowcept.commons.mq_dao import MQDao
from flowcept.commons.doc_db.document_db_dao import DocumentDBDao


class DocumentInserter:
    def __init__(self):
        self._buffer = list()
        self._mq_dao = MQDao()
        self._doc_dao = DocumentDBDao()
        self._previous_time = time()

    def _flush(self):
        self._doc_dao.insert_and_update_many("task_id", self._buffer)
        self._buffer = list()

    def handle_message(self, intercepted_message: Dict):
        if "utc_timestamp" in intercepted_message:
            dt = datetime.fromtimestamp(intercepted_message["utc_timestamp"])
            intercepted_message["timestamp"] = dt.utcnow()

        if DEBUG_MODE:
            intercepted_message["debug"] = True

        self._buffer.append(intercepted_message)
        print("An intercepted message was received.")
        if len(self._buffer) >= MONGO_INSERTION_BUFFER_SIZE:
            print("Buffer exceeded, flushing...")
            self._flush()

    def time_based_flushing(self):
        while True:
            if len(self._buffer):
                now = time()
                timediff = now - self._previous_time
                if timediff >= MONGO_INSERTION_BUFFER_TIME:
                    print("Time to flush!")
                    self._previous_time = now
                    self._flush()
            sleep(MONGO_INSERTION_BUFFER_TIME)

    def main(self):
        Thread(target=self.time_based_flushing).start()
        pubsub = self._mq_dao.subscribe()
        for message in pubsub.listen():
            if message["type"] not in {"psubscribe"}:
                _dict_obj = json.loads(json.loads(message["data"]))
                self.handle_message(_dict_obj)


if __name__ == "__main__":
    try:
        DocumentInserter().main()
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
