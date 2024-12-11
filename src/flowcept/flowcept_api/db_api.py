"""DB API module."""

import uuid
from typing import List, Dict

from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.flowcept_logger import FlowceptLogger


class DBAPI(object):
    """DB API class."""

    # TODO: consider making all methods static
    def __init__(self):
        self.logger = FlowceptLogger()
    @classmethod
    @property
    def _dao(cls) -> DocumentDBDAO:
        return DocumentDBDAO.get_instance(create_indices=False)

    def close(self):
        DBAPI._dao.close()

    def insert_or_update_task(self, task: TaskObject):
        """Insert or update task."""
        return DBAPI._dao.insert_one_task(task.to_dict())

    def insert_or_update_workflow(self, workflow_obj: WorkflowObject) -> WorkflowObject:
        """Insert or update workflow."""
        if workflow_obj.workflow_id is None:
            workflow_obj.workflow_id = str(uuid.uuid4())
        ret = DBAPI._dao.insert_or_update_workflow(workflow_obj)
        if not ret:
            self.logger.error("Sorry, couldn't update or insert workflow.")
            return None
        else:
            return workflow_obj

    def get_workflow_object(self, workflow_id) -> WorkflowObject:
        """Get the workflow from its id."""
        wfobs = self.workflow_query(filter={WorkflowObject.workflow_id_field(): workflow_id})
        if wfobs is None or len(wfobs) == 0:
            self.logger.error("Could not retrieve workflow with that filter.")
            return None
        else:
            return WorkflowObject.from_dict(wfobs[0])

    def workflow_query(self, filter) -> List[Dict]:
        """Query the workflows collection."""
        results = self.query(collection="workflows", filter=filter)
        if results is None:
            self.logger.error("Could not retrieve workflows with that filter.")
            return None
        return results

    def task_query(self,
        filter: Dict,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True) -> List[Dict]:
        """Query the tasks collection."""
        results = self.query(collection="tasks", filter=filter,
                             projection=projection,
                             limit=limit,
                             sort=sort,
                             aggregation=aggregation,
                             remove_json_unserializables=remove_json_unserializables,
                             )
        if results is None:
            self.logger.error("Could not retrieve tasks with that filter.")
            return None
        return results

    def dump_to_file(
        self,
        collection_name="tasks",
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
            DBAPI._dao.dump_to_file(
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
        save_data_in_collection=False,
        pickle=False,
    ):
        """Save the object."""
        return DBAPI._dao.save_object(
            object,
            object_id,
            task_id,
            workflow_id,
            type,
            custom_metadata,
            save_data_in_collection=save_data_in_collection,
            pickle_=pickle,
        )

    def to_df(self, collection="tasks", filter=None):
        """Return a dataframe given the filter."""
        return DBAPI._dao.to_df(collection, filter)

    def query(
        self,
        collection="tasks",
        filter=None,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
    ):
        """Query it."""
        return DBAPI._dao.query(
            collection, filter, projection, limit, sort, aggregation, remove_json_unserializables
        )

    def save_torch_model(
        self,
        model,
        task_id=None,
        workflow_id=None,
        custom_metadata: dict = {},
    ) -> str:
        """Save model.

        Save the PyTorch model state_dict to a MongoDB collection as binary data.

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

    def load_torch_model(self, model, object_id: str):
        """Load a torch model stored in the database.

        Args:
            model (torch.nn.Module): An empty PyTorch model to be loaded. The class of this model
            in argument should be the same of the model that was saved.
            object_id (str): Id of the object stored in the objects collection.
        """
        import torch
        import io

        doc = self.query(collection="objects", filter={"object_id": object_id})[0]

        if "data" in doc:
            binary_data = doc["data"]
        else:
            file_id = doc["grid_fs_file_id"]
            binary_data = DBAPI._dao.get_file_data(file_id)

        buffer = io.BytesIO(binary_data)
        state_dict = torch.load(buffer, weights_only=True)
        model.load_state_dict(state_dict)

        return model
