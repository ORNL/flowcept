from threading import Thread
from time import sleep

from flowcept.commons.doc_db.document_inserter import DocumentInserter

from typing import List

from flowcept.flowceptor.plugins.base_interceptor import BaseInterceptor


class FlowceptConsumerAPI(object):
    def __init__(self, interceptors: List[BaseInterceptor] = None):
        self._consumer_thread: Thread = None
        if interceptors is not None and type(interceptors) != list:
            interceptors = [interceptors]
        self._interceptors = interceptors

    def start(self):
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                print(f"Flowceptor {interceptor.settings.key} starting...")
                Thread(target=interceptor.observe).start()
                print("... ok!")

        print("Flowcept Consumer starting...")
        self._consumer_thread = Thread(target=DocumentInserter().main)
        self._consumer_thread.start()
        sleep(2)
        print("Ok, we're consuming messages!")
