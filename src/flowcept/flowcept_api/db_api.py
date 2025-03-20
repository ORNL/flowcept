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

    ASCENDING = 1
    DESCENDING = -1

    # TODO: consider making all methods static
    def __init__(self):
        self.logger = FlowceptLogger()

    @classmethod
    def _dao(cls) -> DocumentDBDAO:
        return DocumentDBDAO.get_instance(create_indices=False)

    def close(self):
        """Close DB resources."""
        DBAPI._dao().close()

    def insert_or_update_task(self, task: TaskObject):
        """Insert or update task."""
        return DBAPI._dao().insert_one_task(task.to_dict())

    def insert_or_update_workflow(self, workflow_obj: WorkflowObject) -> WorkflowObject:
        """Insert or update workflow."""
        if workflow_obj.workflow_id is None:
            workflow_obj.workflow_id = str(uuid.uuid4())
        self.logger.debug(f"DB API going to save workflow {workflow_obj}")
        ret = DBAPI._dao().insert_or_update_workflow(workflow_obj)
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

    def get_tasks_from_current_workflow(self):
        """
        Get the tasks of the current workflow in the Flowcept instance.
        """
        from flowcept.flowcept_api.flowcept_controller import Flowcept

        return self.task_query(filter={"workflow_id": Flowcept.current_workflow_id})

    def task_query(
        self,
        filter: Dict,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
    ) -> List[Dict]:
        """Query the tasks collection."""
        results = self.query(
            collection="tasks",
            filter=filter,
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

    def get_tasks_recursive(self, workflow_id, max_depth=999, mapping=None):
        """
        Retrieve all tasks recursively for a given workflow ID.

        This method fetches a workflow's root task and all its child tasks recursively
        using the data access object (DAO). The recursion depth can be controlled
        using the `max_depth` parameter to prevent excessive recursion.

        Parameters
        ----------
        workflow_id : str
            The ID of the workflow for which tasks need to be retrieved.
        max_depth : int, optional
            The maximum depth to traverse in the task hierarchy (default is 999).
            Helps avoid excessive recursion for workflows with deeply nested tasks.

        Returns
        -------
        list of dict
            A list of tasks represented as dictionaries, including parent and child tasks
            up to the specified recursion depth.

        Raises
        ------
        Exception
            If an error occurs during retrieval, it is logged and re-raised.

        Notes
        -----
        This method delegates the operation to the DAO implementation.
        """
        try:
            return DBAPI._dao().get_tasks_recursive(workflow_id, max_depth, mapping)
        except Exception as e:
            self.logger.exception(e)
            raise e

    def dump_tasks_to_file_recursive(self, workflow_id, output_file="tasks.parquet", max_depth=999, mapping=None):
        """
        Dump tasks recursively for a given workflow ID to a file.

        This method retrieves all tasks (parent and children) for the given workflow ID
        up to a specified recursion depth and saves them to a file in Parquet format.

        Parameters
        ----------
        workflow_id : str
            The ID of the workflow for which tasks need to be retrieved and saved.
        output_file : str, optional
            The name of the output file to save tasks (default is "tasks.parquet").
        max_depth : int, optional
            The maximum depth to traverse in the task hierarchy (default is 999).
            Helps avoid excessive recursion for workflows with deeply nested tasks.

        Returns
        -------
        None

        Raises
        ------
        Exception
            If an error occurs during the file dump operation, it is logged and re-raised.

        Notes
        -----
        The method delegates the task retrieval and saving operation to the DAO implementation.
        """
        try:
            return DBAPI._dao().dump_tasks_to_file_recursive(workflow_id, output_file, max_depth, mapping)
        except Exception as e:
            self.logger.exception(e)
            raise e

    def dump_to_file(
        self,
        collection="tasks",
        filter=None,
        output_file=None,
        export_format="json",
        should_zip=False,
    ):
        """Dump to the file."""
        if filter is None and not should_zip:
            self.logger.error("Not allowed to dump entire database without filter and without zipping it.")
            return False
        try:
            DBAPI._dao().dump_to_file(
                collection,
                filter,
                output_file,
                export_format,
                should_zip,
            )
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def save_or_update_object(
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
        return DBAPI._dao().save_or_update_object(
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
        return DBAPI._dao().to_df(collection, filter)

    def query(
        self,
        filter=None,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
        collection="tasks",
    ):
        """Query it."""
        return DBAPI._dao().query(filter, projection, limit, sort, aggregation, remove_json_unserializables, collection)

    def save_or_update_torch_model(
        self,
        model,
        object_id=None,
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
        obj_id = self.save_or_update_object(
            object=binary_data,
            object_id=object_id,
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
            binary_data = DBAPI._dao().get_file_data(file_id)

        buffer = io.BytesIO(binary_data)
        state_dict = torch.load(buffer, weights_only=True)
        model.load_state_dict(state_dict)

        return doc
