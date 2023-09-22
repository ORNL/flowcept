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
class TaskMessage:
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
    environment_id: AnyStr = None
    node_name: AnyStr = None
    login_name: AnyStr = None
    public_ip: AnyStr = None
    private_ip: AnyStr = None
    hostname: AnyStr = None
    extra_metadata: Dict = None
    sys_name: AnyStr = None
    address: AnyStr = None
    dependencies: List = None
    dependents: List = None
    flowcept_version: str = None

    @staticmethod
    def get_dict_field_names():
        return [
            "used",
            "generated",
            "custom_metadata",
            "start_telemetry",
            "end_telemetry",
        ]

    @staticmethod
    def get_index_field():
        return "task_id"

    @staticmethod
    def get_workflow_id_field():
        return "workflow_id"

    def to_dict(self):
        ret = self.__dict__
        if self.telemetry_at_start is not None:
            ret["telemetry_at_start"] = self.telemetry_at_start.to_dict()
        if self.telemetry_at_end is not None:
            ret["telemetry_at_end"] = self.telemetry_at_end.to_dict()
        return ret
