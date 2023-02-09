from typing import List
from threading import Thread, Event
from time import sleep
from flowcept.commons.doc_db.document_inserter import DocumentInserter
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.plugins.base_interceptor import BaseInterceptor


class FlowceptConsumerAPI(object):
    def __init__(self, interceptors: List[BaseInterceptor] = None):
        self._document_inserter: DocumentInserter = None
        self.logger = FlowceptLogger().get_logger()
        self._consumer_thread: Thread = None
        if interceptors is not None and type(interceptors) != list:
            interceptors = [interceptors]
        self._interceptors: List[BaseInterceptor] = interceptors

    def start(self):
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                self.logger.debug(
                    f"Flowceptor {interceptor.settings.key} starting..."
                )
                interceptor.start()
                self.logger.debug("... ok!")

        # self._stop_event = Event()
        self.logger.debug("Flowcept Consumer starting...")
        self._document_inserter = DocumentInserter().start()
        sleep(2)
        self.logger.debug("Ok, we're consuming messages!")

    def stop(self):
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                self.logger.debug(
                    f"Flowceptor {interceptor.settings.key} stopping..."
                )
                interceptor.stop()
                self.logger.debug("... ok!")
        self.logger.debug("Stopping Consumer...")
        self._document_inserter.stop()
        self.logger.debug("All stopped!")