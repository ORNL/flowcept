from typing import List, Union
from time import sleep

import flowcept.instrumentation.decorators
from flowcept.commons import logger
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.daos.mq_dao import MQDao
from flowcept.configs import REDIS_INSTANCES
from flowcept.flowceptor.consumers.document_inserter import DocumentInserter
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor


# TODO: :code-reorg: This may not be considered an API anymore as it's doing critical things for the good functioning of the system.
class FlowceptConsumerAPI(object):
    def __init__(
        self,
        interceptors: Union[
            BaseInterceptor, List[BaseInterceptor]
        ] = flowcept.instrumentation.decorators.instrumentation_interceptor,
        bundle_exec_id=None,
        start_doc_inserter=True,
    ):
        self.logger = FlowceptLogger()

        self._document_inserters: List[DocumentInserter] = []
        self._start_doc_inserter = start_doc_inserter
        if bundle_exec_id is None:
            self._bundle_exec_id = id(self)
        else:
            self._bundle_exec_id = bundle_exec_id
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
                # TODO: :base-interceptor-refactor: revise
                if interceptor.settings is None:
                    key = id(interceptor)
                else:
                    key = interceptor.settings.key
                self.logger.debug(f"Flowceptor {key} starting...")
                interceptor.start(bundle_exec_id=self._bundle_exec_id)
                self.logger.debug(f"...Flowceptor {key} started ok!")

        if self._start_doc_inserter:
            self.logger.debug("Flowcept Consumer starting...")

            if REDIS_INSTANCES is not None and len(REDIS_INSTANCES):
                for mq_host_port in REDIS_INSTANCES:
                    split = mq_host_port.split(":")
                    mq_host = split[0]
                    mq_port = int(split[1])
                    self._document_inserters.append(
                        DocumentInserter(
                            check_safe_stops=True,
                            mq_host=mq_host,
                            mq_port=mq_port,
                            bundle_exec_id=self._bundle_exec_id,
                        ).start()
                    )
            else:
                self._document_inserters.append(
                    DocumentInserter(
                        check_safe_stops=True,
                        bundle_exec_id=self._bundle_exec_id,
                    ).start()
                )
        self.logger.debug("Ok, we're consuming messages!")
        self.is_started = True
        return self

    def stop(self):
        if not self.is_started:
            self.logger.warning("Consumer is already stopped!")
            return
        sleep_time = 1
        self.logger.info(
            f"Received the stop signal. We're going to wait {sleep_time} secs."
            f" before gracefully stopping..."
        )
        sleep(sleep_time)
        if self._interceptors and len(self._interceptors):
            for interceptor in self._interceptors:
                # TODO: :base-interceptor-refactor: revise
                if interceptor.settings is None:
                    key = id(interceptor)
                else:
                    key = interceptor.settings.key
                self.logger.info(f"Flowceptor {key} stopping...")
                interceptor.stop()
        if self._start_doc_inserter:
            self.logger.info("Stopping Doc Inserters...")
            for doc_inserter in self._document_inserters:
                doc_inserter.stop(bundle_exec_id=id(self))
        self.is_started = False
        self.logger.debug("All stopped!")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()

    @staticmethod
    def services_alive() -> bool:
        if not MQDao().liveness_test():
            logger.error("MQ Not Ready!")
            return False
        if not DocumentDBDao().liveness_test():
            logger.error("DocDB Not Ready!")
            return False
        logger.info("MQ and DocDB are alive!")
        return True
