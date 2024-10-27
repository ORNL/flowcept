"""DB module."""

import uuid
from typing import List

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
    """DB class."""

    def __init__(
        self,
        with_webserver=False,
    ):
        self.logger = FlowceptLogger()
        self.with_webserver = with_webserver
        if self.with_webserver:
            raise NotImplementedError("We did not implement webserver API for this yet.")

        self._dao = DocumentDBDao()

    def insert_or_update_task(self, task: TaskObject):
        """Insert or update task."""
        self._dao.insert_one(task.to_dict())

    def insert_or_update_workflow(self, workflow_obj: WorkflowObject) -> WorkflowObject:
        """Insert or update workflow."""
        if workflow_obj.workflow_id is None:
            workflow_obj.workflow_id = str(uuid.uuid4())
        ret = self._dao.workflow_insert_or_update(workflow_obj)
        if not ret:
            self.logger.error("Sorry, couldn't update or insert workflow.")
            return None
        else:
            return workflow_obj

    def get_workflow(self, workflow_id) -> WorkflowObject:
        """Get the workflow."""
        wfobs = self.workflow_query(filter={WorkflowObject.workflow_id_field(): workflow_id})
        if wfobs is None or len(wfobs) == 0:
            self.logger.error("Could not retrieve workflow with that filter.")
            return None
        else:
            return wfobs[0]

    def workflow_query(self, filter) -> List[WorkflowObject]:
        """Get workflow query."""
        results = self._dao.workflow_query(filter=filter)
        if results is None:
            self.logger.error("Could not retrieve workflow with that filter.")
            return None
        if len(results):
            try:
                lst = []
                for wf_dict in results:
                    lst.append(WorkflowObject.from_dict(wf_dict))
                return lst
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
        """Dump to the file."""
        if filter is None and not should_zip:
            self.logger.error(
                "Not allowed to dump entire database without filter and without zipping it."
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

    def save_object(
        self,
        object,
        object_id=None,
        task_id=None,
        workflow_id=None,
        type=None,
        custom_metadata=None,
        pickle=False,
    ):
        """Save the object."""
        return self._dao.save_object(
            object,
            object_id,
            task_id,
            workflow_id,
            type,
            custom_metadata,
            pickle_=pickle,
        )

    def query(
        self,
        filter=None,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
        type="task",
    ):
        """Query it."""
        if type == "task":
            return self._dao.task_query(
                filter,
                projection,
                limit,
                sort,
                aggregation,
                remove_json_unserializables,
            )
        elif type == "workflow":
            return self._dao.workflow_query(
                filter, projection, limit, sort, remove_json_unserializables
            )
        elif type == "object":
            return self._dao.get_objects(filter)
        else:
            raise Exception(
                f"You used type={type}, but we only have " f"collections for task and workflow."
            )

    def save_torch_model(
        self,
        model,
        task_id=None,
        workflow_id=None,
        custom_metadata: dict = None,
    ) -> str:
        """Save model.

        Save the PyTorch model's state_dict to a MongoDB collection as binary data.

        Args:
            model (torch.nn.Module): The PyTorch model to be saved.
            custom_metadata (Dict[str, str]): Custom metadata to be stored with the model.

        Returns
        -------
            str: The object ID of the saved model in the database.
        """
        import torch
        import io

        state_dict = model.state_dict()
        buffer = io.BytesIO()
        torch.save(state_dict, buffer)
        buffer.seek(0)
        binary_data = buffer.read()
        cm = {
            **custom_metadata,
            "class": model.__class__.__name__,
        }
        obj_id = self.save_object(
            object=binary_data,
            type="ml_model",
            task_id=task_id,
            workflow_id=workflow_id,
            custom_metadata=cm,
        )

        return obj_id

    def load_torch_model(self, torch_model, object_id: str):
        """Load it."""
        import torch
        import io

        doc = self.query({"object_id": object_id}, type="object")[0]
        binary_data = doc["data"]

        buffer = io.BytesIO(binary_data)
        state_dict = torch.load(buffer, weights_only=True)
        torch_model.load_state_dict(state_dict)

        return torch_model
