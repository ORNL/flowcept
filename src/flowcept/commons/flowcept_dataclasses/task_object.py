"""Task object module."""

from typing import Dict, AnyStr, Any, Union, List
import msgpack

import flowcept
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry
from flowcept.commons.vocabulary import Status
from flowcept.configs import (
    HOSTNAME,
    PRIVATE_IP,
    PUBLIC_IP,
    LOGIN_NAME,
    NODE_NAME,
)


class TaskObject:
    """Task object class.

    Represents a single provenance task in Flowcept, including inputs, outputs,
    execution metadata, telemetry, and environment details.
    """

    type = "task"
    """Constant type label for this object ("task")."""

    subtype: AnyStr = None
    """Optional subtype of the task (e.g., iteration, ML step, custom)."""

    task_id: AnyStr = None
    """Unique identifier of the task."""

    utc_timestamp: float = None
    """UTC timestamp when the task object was created."""

    adapter_id: AnyStr = None
    """Identifier of the adapter that produced this task (if any)."""

    user: AnyStr = None
    """User who executed or triggered the task."""

    data: Any = None
    """Arbitrary raw data payload associated with the task. It is good practice to add custom_metadata associated with
    `data`, especially if it contains file contents. 
    In that case, `custom_metadata` should contain the keys "file_type", "file_content", "file_name", "extension".
    """

    used: Dict[AnyStr, Any] = None
    """Inputs consumed by the task (parameters, files, resources)."""

    campaign_id: AnyStr = None
    """Campaign identifier grouping related tasks together."""

    generated: Dict[AnyStr, Any] = None
    """Outputs produced by the task (results, artifacts, files)."""

    submitted_at: float = None
    """Timestamp when the task was submitted."""

    started_at: float = None
    """Timestamp when the task execution started."""

    ended_at: float = None
    """Timestamp when the task execution ended."""

    registered_at: float = None
    """Timestamp when the task was registered by the DocInserter."""

    telemetry_at_start: Telemetry = None
    """Telemetry snapshot captured at the start of the task."""

    telemetry_at_end: Telemetry = None
    """Telemetry snapshot captured at the end of the task."""

    workflow_name: AnyStr = None
    """Name of the workflow this task belongs to."""

    workflow_id: AnyStr = None
    """Identifier of the workflow this task belongs to."""

    parent_task_id: AnyStr = None
    """Identifier of the parent task, if this task is nested or dependent."""

    activity_id: AnyStr = None
    """Activity name (usually the function name) associated with the task."""

    group_id: AnyStr = None
    """Grouping identifier, often used to link loop iterations together."""

    status: Status = None
    """Execution status of the task (e.g., FINISHED, ERROR)."""

    stdout: Union[AnyStr, Dict] = None
    """Captured standard output from the task, if available."""

    stderr: Union[AnyStr, Dict] = None
    """Captured standard error from the task, if available."""

    custom_metadata: Dict[AnyStr, Any] = None
    """Custom metadata dictionary provided by the developer/user."""

    mq_host: str = None
    """Message queue host associated with the task."""

    environment_id: AnyStr = None
    """Identifier of the environment where the task executed."""

    node_name: AnyStr = None
    """Node name in a distributed system or HPC cluster."""

    login_name: AnyStr = None
    """Login name of the user in the execution environment."""

    public_ip: AnyStr = None
    """Public IP address of the machine executing the task."""

    private_ip: AnyStr = None
    """Private IP address of the machine executing the task."""

    hostname: AnyStr = None
    """Hostname of the machine executing the task."""

    address: AnyStr = None
    """Optional network address associated with the task."""

    dependencies: List = None
    """List of task IDs this task depends on."""

    dependents: List = None
    """List of task IDs that depend on this task."""

    tags: List = None
    """User-defined tags attached to the task."""

    agent_id: str = None
    """Identifier of the agent responsible for executing this task (if any)."""

    _DEFAULT_ENRICH_VALUES = {
        "node_name": NODE_NAME,
        "login_name": LOGIN_NAME,
        "public_ip": PUBLIC_IP,
        "private_ip": PRIVATE_IP,
        "hostname": HOSTNAME,
    }

    @staticmethod
    def get_time_field_names():
        """Get the time field."""
        return [
            "started_at",
            "ended_at",
            "submitted_at",
            "registered_at",
            "utc_timestamp",
        ]

    @staticmethod
    def get_dict_field_names():
        """Get field names."""
        return [
            "used",
            "generated",
            "custom_metadata",
            "telemetry_at_start",
            "telemetry_at_end",
        ]

    @staticmethod
    def task_id_field():
        """Get task id."""
        return "task_id"

    @staticmethod
    def workflow_id_field():
        """Get workflow id."""
        return "workflow_id"

    def enrich(self, adapter_key=None):
        """Enrich it."""
        if adapter_key is not None:
            # TODO :base-interceptor-refactor: :code-reorg: :usability:
            # revisit all times we assume settings is not none
            self.adapter_id = adapter_key

        if self.utc_timestamp is None:
            self.utc_timestamp = flowcept.commons.utils.get_utc_now()

        for key, fallback_value in TaskObject._DEFAULT_ENRICH_VALUES.items():
            if getattr(self, key) is None and fallback_value is not None:
                setattr(self, key, fallback_value)

    @staticmethod
    def enrich_task_dict(task_dict: dict):
        """Enrich the task."""
        for key, fallback_value in TaskObject._DEFAULT_ENRICH_VALUES.items():
            if (key not in task_dict or task_dict[key] is None) and fallback_value is not None:
                task_dict[key] = fallback_value

    def to_dict(self):
        """Convert to dictionary."""
        result_dict = {}
        for attr, value in self.__dict__.items():
            if value is not None:
                if attr == "telemetry_at_start":
                    result_dict[attr] = self.telemetry_at_start.to_dict()
                elif attr == "telemetry_at_end":
                    result_dict[attr] = self.telemetry_at_end.to_dict()
                elif attr == "status":
                    result_dict[attr] = value.value
                else:
                    result_dict[attr] = value
        result_dict["type"] = "task"
        return result_dict

    def serialize(self):
        """Serialize it."""
        return msgpack.dumps(self.to_dict())

    @staticmethod
    def from_dict(task_obj_dict: Dict[AnyStr, Any]) -> "TaskObject":
        """Create a TaskObject from a dictionary.

        Parameters
        ----------
        task_obj_dict : Dict[AnyStr, Any]
            Dictionary containing task attributes.

        Returns
        -------
        TaskObject
            A TaskObject instance populated with available data.
        """
        task = TaskObject()

        for key, value in task_obj_dict.items():
            if hasattr(task, key):
                if key == "status" and isinstance(value, str):
                    setattr(task, key, Status(value))
                else:
                    setattr(task, key, value)

        return task

    def __str__(self):
        """Return a user-friendly string representation of the TaskObject."""
        return self.__repr__()

    def __repr__(self):
        """Return an unambiguous string representation of the TaskObject."""
        attrs = ["task_id", "workflow_id", "campaign_id", "activity_id", "started_at", "ended_at"]
        optionals = ["subtype", "parent_task_id", "agent_id"]
        for opt in optionals:
            if getattr(self, opt) is not None:
                attrs.append(opt)
        attr_str = ", ".join(f"{attr}={repr(getattr(self, attr))}" for attr in attrs)
        return f"TaskObject({attr_str})"
