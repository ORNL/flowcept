from typing import Dict

from flowcept.version import __version__
from flowcept.commons.daos.document_db_dao import DocumentDBDao
from flowcept.commons.flowcept_dataclasses.task_message import TaskMessage
from flowcept.commons.flowcept_logger import FlowceptLogger


class DBAPI(object):
    def __init__(
        self,
        with_webserver=False,
    ):
        self.logger = FlowceptLogger().get_logger()
        self.with_webserver = with_webserver
        if self.with_webserver:
            raise NotImplementedError(
                f"We did not implement webserver API for this yet."
            )

        self._dao = DocumentDBDao()

    def insert_or_update_workflow(
        self,
        workflow_id: str,
        custom_metadata: Dict = None,
        comment: str = None,
    ) -> bool:
        wf_data = dict()
        if custom_metadata is not None:
            wf_data["custom_metadata"] = custom_metadata
        wf_data["flowcept_version"] = __version__
        if comment is not None:
            wf_data["comment"] = comment

        return self._dao.workflow_insert_or_update(workflow_id, wf_data)

    def get_workflow(self, workflow_id):
        results = self._dao.workflow_query(
            filter={TaskMessage.get_workflow_id_field(): workflow_id}
        )
        if results is None:
            self.logger.error("Could not retrieve workflow")
            return None
        if len(results):
            return results[0]
