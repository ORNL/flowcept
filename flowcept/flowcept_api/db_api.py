from typing import Dict

from flowcept.commons.decorators import singleton
from flowcept.configs import MONGO_TASK_COLLECTION
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_dataclasses.task_message import TaskMessage
from flowcept.commons.flowcept_logger import FlowceptLogger


@singleton
class DBAPI(object):
    def __init__(
        self,
        with_webserver=False,
    ):
        self.logger = FlowceptLogger()
        self.with_webserver = with_webserver
        if self.with_webserver:
            raise NotImplementedError(
                f"We did not implement webserver API for this yet."
            )

        self._dao = DocumentDBDao()

    def insert_or_update_task(self, task: TaskMessage):
        self._dao.insert_one(task.to_dict())

    def insert_or_update_workflow(
        self, workflow_id: str, workflow_info: Dict = {}
    ) -> bool:
        return self._dao.workflow_insert_or_update(workflow_id, workflow_info)

    def get_workflow(self, workflow_id):
        results = self._dao.workflow_query(
            filter={TaskMessage.get_workflow_id_field(): workflow_id}
        )
        if results is None:
            self.logger.error("Could not retrieve workflow")
            return None
        if len(results):
            return results[0]

    def dump_to_file(
        self,
        collection_name=MONGO_TASK_COLLECTION,
        filter=None,
        output_file=None,
        export_format="json",
        should_zip=False,
    ):
        if filter is None and not should_zip:
            self.logger.error(
                "I am sorry, we will not allow you to dump the entire database without filter and without even zipping it. You are likely doing something wrong or perhaps not using the best tool for a database dump."
            )
            return False
        try:
            self._dao.dump_to_file(
                collection_name,
                filter,
                output_file,
                export_format,
                should_zip,
            )
            return True
        except Exception as e:
            self.logger.exception(e)
            return False
