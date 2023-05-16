from typing import List, Union
from time import sleep
import random
from flowcept.configs import REDIS_INSERTION_BUFFER_TIME, MONGO_INSERTION_BUFFER_TIME
from flowcept.flowceptor.consumers.document_inserter import DocumentInserter
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.plugins.base_interceptor import BaseInterceptor


class FlowceptConsumerAPI(object):
    def __init__(
        self,
        interceptors: Union[BaseInterceptor, List[BaseInterceptor]] = None,
    ):
        self.logger = FlowceptLogger().get_logger()
        self._document_inserter: DocumentInserter = None
        if interceptors is not None and type(interceptors) != list:
            interceptors = [interceptors]
        self._interceptors: List[BaseInterceptor] = interceptors
        self.is_started = False

    def start(self):
        if self.is_started:
            self.logger.warning("Consumer is already started!")
            return self

        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                self.logger.debug(
                    f"Flowceptor {interceptor.settings.key} starting..."
                )
                interceptor.start()
                self.logger.debug("... ok!")

        self.logger.debug("Flowcept Consumer starting...")
        self._document_inserter = DocumentInserter().start()
        sleep(2)
        self.logger.debug("Ok, we're consuming messages!")
        self.is_started = True
        return self

    def stop(self):
        if not self.is_started:
            self.logger.warning("Consumer is already stopped!")
            return

        # TODO: we should not need to wait that long, but I couldn't solve it
        #  properly yet. Currently, it has to be greater the insertion sleeps
        sleep_time = max(MONGO_INSERTION_BUFFER_TIME, REDIS_INSERTION_BUFFER_TIME) * 4
        self.logger.debug(f"Received the stop signal. We're going to wait {sleep_time} s before gracefully stopping...")
        sleep(sleep_time)
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                self.logger.debug(
                    f"Flowceptor {interceptor.settings.key} stopping..."
                )
                interceptor.stop()
                self.logger.debug("... ok!")
        self.logger.debug("Stopping Consumer...")
        self._document_inserter.stop()
        self.is_started = False
        self.logger.debug("All stopped!")
