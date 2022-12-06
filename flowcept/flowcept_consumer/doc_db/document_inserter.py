from typing import Dict
import json
import sys
from time import time

from flowcept.configs import (
    MONGO_INSERTION_BUFFER_TIME,
    MONGO_INSERTION_BUFFER_SIZE
)

from flowcept.commons.mq_dao import MQDao
from flowcept.flowcept_consumer.doc_db.document_db_dao import DocumentDBDao


class DocumentInserter:

    BUFFER_SIZE = MONGO_INSERTION_BUFFER_SIZE
    FLUSH_TIME = MONGO_INSERTION_BUFFER_TIME  # secs.

    def __init__(self):
        self.buffer = list()
        self.counter = 0
        self.mq_dao = MQDao()
        self.doc_dao = DocumentDBDao()
        self._previous_time = time()

    def _flush(self):
        self.doc_dao.insert_many(self.buffer)
        self.buffer = list()

    def handle_message(self, intercepted_message: Dict):
        self.buffer.append(intercepted_message)
        print("An intercepted message was received.")
        if len(self.buffer) >= DocumentInserter.BUFFER_SIZE:
            print("Buffer exceeded, flushing...")
            self._flush()
        else:
            now = time()
            timediff = now - self._previous_time
            if timediff > DocumentInserter.FLUSH_TIME:
                print("Time to flush!")
                self._previous_time = now
                self._flush()

    def main(self):
        pubsub = self.mq_dao.subscribe()
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
