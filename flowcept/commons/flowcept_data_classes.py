from enum import Enum
from typing import Dict, AnyStr, Any, Union


class Status(str, Enum):  # inheriting from str here for JSON serialization
    SUBMITTED = "SUBMITTED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"

    @staticmethod
    def get_finished_statuses():
        return [Status.FINISHED, Status.ERROR]


# Not a dataclass because a dataclass stores keys even when there's no value,
# adding unnecessary overhead.
class TaskMessage:

    task_id: AnyStr = None  # Any way to identify a task
    utc_timestamp: float = None  # TODO: remove this from all plugins
    plugin_id: AnyStr = None
    user: AnyStr = None
    msg_id: AnyStr = None  # TODO: Remove this from all plugins in the future
    used: Dict[AnyStr, Any] = None  # Used parameter and files
    experiment_id: AnyStr = None
    generated: Dict[AnyStr, Any] = None  # Generated results and files
    start_time: float = None
    end_time: float = None
    workflow_id: AnyStr = None
    activity_id: AnyStr = None
    status: Status = None
    stdout: Union[AnyStr, Dict] = None
    stderr: Union[AnyStr, Dict] = None
    custom_metadata: Dict[AnyStr, Any] = None
    node_name: AnyStr = None
    login_name: AnyStr = None
    public_ip: AnyStr = None
    private_ip: AnyStr = None
    sys_name: AnyStr = None
    address: AnyStr = None

    @staticmethod
    def get_dict_field_names():
        return ["used", "generated", "custom_metadata"]
