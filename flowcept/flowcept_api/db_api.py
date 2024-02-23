import uuid
from typing import Dict

from flowcept.commons import singleton
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.configs import MONGO_TASK_COLLECTION
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
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

    def insert_or_update_task(self, task: TaskObject):
        self._dao.insert_one(task.to_dict())

    def insert_or_update_workflow(
        self, workflow_obj: WorkflowObject
    ) -> WorkflowObject:
        if workflow_obj.workflow_id is None:
            workflow_obj.workflow_id = str(uuid.uuid4())
        ret = self._dao.workflow_insert_or_update(workflow_obj)
        if not ret:
            self.logger.error("Sorry, couldn't update or insert workflow.")
            return None
        else:
            return workflow_obj

    def get_workflow(self, workflow_id) -> WorkflowObject:
        return self.workflow_query(
            filter={TaskObject.workflow_id_field(): workflow_id}
        )

    def workflow_query(self, filter) -> WorkflowObject:
        results = self._dao.workflow_query(filter=filter)
        if results is None:
            self.logger.error("Could not retrieve workflow with that filter.")
            return None
        if len(results):
            try:
                return WorkflowObject(**results[0])
            except Exception as e:
                self.logger.exception(e)
                return None

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
