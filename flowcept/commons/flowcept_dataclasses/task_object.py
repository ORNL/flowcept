from enum import Enum
from typing import Dict, AnyStr, Any, Union, List

from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry


class Status(str, Enum):  # inheriting from str here for JSON serialization
    SUBMITTED = "SUBMITTED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

    @staticmethod
    def get_finished_statuses():
        return [Status.FINISHED, Status.ERROR]


# Not a dataclass because a dataclass stores keys even when there's no value,
# adding unnecessary overhead.
class TaskObject:
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
    def get_dict_field_names():
        return [
            "used",
            "generated",
            "custom_metadata",
            "telemetry_at_start",
            "telemetry_at_end",
        ]

    @staticmethod
    def task_id_field():
        return "task_id"

    @staticmethod
    def workflow_id_field():
        return "workflow_id"

    def to_dict(self):
        result_dict = {}
        for attr, value in self.__dict__.items():
            if value is not None:
                if attr == "telemetry_at_start":
                    result_dict[attr] = self.telemetry_at_start.to_dict()
                elif attr == "telemetry_at_end":
                    result_dict[attr] = self.telemetry_at_end.to_dict()
                else:
                    result_dict[attr] = value
        result_dict["type"] = "task"
        return result_dict
