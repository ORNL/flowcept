from enum import Enum
from typing import Dict, AnyStr, Any


class Status(Enum):
    SUBMITTED = "SUBMITTED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"


# Not a dataclass because a dataclass stores keys even when there's no value,
# adding unnecessary overhead.
class TaskMessage:

    task_id: AnyStr = None  # Any way to identify a task
    utc_timestamp: float = None
    plugin_id: AnyStr = None
    user: AnyStr = None
    msg_id: AnyStr = None  # TODO: Remove this in all plugins in the future
    used: Dict[AnyStr, Any] = None  # Used parameter and files
    experiment_id: AnyStr = None
    generated: Dict[AnyStr, Any] = None  # Generated results and files
    start_time: float = None
    end_time: float = None
    workflow_id: AnyStr = None
    activity_id: AnyStr = None
    status: Status = None
    stdout: AnyStr = None
    stderr: AnyStr = None
    custom_metadata: Dict[AnyStr, Any] = None
    node_name: AnyStr = None
    login_name: AnyStr = None
    public_ip: AnyStr = None
    private_ip: AnyStr = None
    sys_name: AnyStr = None
