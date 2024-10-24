"""Task object module."""

from enum import Enum
from typing import Dict, AnyStr, Any, Union, List
import msgpack

import flowcept
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry
from flowcept.configs import (
    HOSTNAME,
    PRIVATE_IP,
    PUBLIC_IP,
    LOGIN_NAME,
    NODE_NAME,
    CAMPAIGN_ID,
)


class Status(str, Enum):
    """Status class.

    Inheriting from str here for JSON serialization.
    """

    SUBMITTED = "SUBMITTED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

    @staticmethod
    def get_finished_statuses():
        """Get finished status."""
        return [Status.FINISHED, Status.ERROR]


class TaskObject:
    """Task class."""

    type = "task"
    task_id: AnyStr = None  # Any way to identify a task
    utc_timestamp: float = None
    adapter_id: AnyStr = None
    user: AnyStr = None
    used: Dict[AnyStr, Any] = None  # Used parameter and files
    campaign_id: AnyStr = None
    generated: Dict[AnyStr, Any] = None  # Generated results and files
    submitted_at: float = None
    started_at: float = None
    ended_at: float = None
    registered_at: float = None
    telemetry_at_start: Telemetry = None
    telemetry_at_end: Telemetry = None
    workflow_name: AnyStr = None
    workflow_id: AnyStr = None
    activity_id: AnyStr = None
    status: Status = None
    stdout: Union[AnyStr, Dict] = None
    stderr: Union[AnyStr, Dict] = None
    custom_metadata: Dict[AnyStr, Any] = None
    mq_host: str = None
    environment_id: AnyStr = None
    node_name: AnyStr = None
    login_name: AnyStr = None
    public_ip: AnyStr = None
    private_ip: AnyStr = None
    hostname: AnyStr = None
    address: AnyStr = None
    dependencies: List = None
    dependents: List = None

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

        if self.campaign_id is None:
            self.campaign_id = CAMPAIGN_ID

        if self.node_name is None and NODE_NAME is not None:
            self.node_name = NODE_NAME

        if self.login_name is None and LOGIN_NAME is not None:
            self.login_name = LOGIN_NAME

        if self.public_ip is None and PUBLIC_IP is not None:
            self.public_ip = PUBLIC_IP

        if self.private_ip is None and PRIVATE_IP is not None:
            self.private_ip = PRIVATE_IP

        if self.hostname is None and HOSTNAME is not None:
            self.hostname = HOSTNAME

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
    def enrich_task_dict(task_dict: dict):
        """Enrich the task."""
        attributes = {
            "campaign_id": CAMPAIGN_ID,
            "node_name": NODE_NAME,
            "login_name": LOGIN_NAME,
            "public_ip": PUBLIC_IP,
            "private_ip": PRIVATE_IP,
            "hostname": HOSTNAME,
        }
        for key, fallback_value in attributes.items():
            if (key not in task_dict or task_dict[key] is None) and fallback_value is not None:
                task_dict[key] = fallback_value

    # @staticmethod
    # def deserialize(serialized_data) -> 'TaskObject':
    #     dict_obj = msgpack.loads(serialized_data)
    #     obj = TaskObject()
    #     for k, v in dict_obj.items():
    #         setattr(obj, k, v)
    #     return obj
