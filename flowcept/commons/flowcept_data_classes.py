from dataclasses import dataclass
from typing import Dict, AnyStr, Any


@dataclass
class TaskMessage:

    plugin_id: AnyStr
    used: Dict[AnyStr, Any]  # Used parameter and files
    msg_id: AnyStr
    task_id: AnyStr  # Any way to identify a task
    user: AnyStr
    utc_timestamp: float
    experiment_id: AnyStr = None
    generated: Dict[AnyStr, Any] = None  # Generated results and files
    start_time: float = None
    end_time: float = None
    workflow_id: AnyStr = None
    activity_id: AnyStr = None
    status: AnyStr = None
    stdout: AnyStr = None
    stderr: AnyStr = None
    custom_metadata: Dict[AnyStr, Any] = None
    node_name: AnyStr = None
    login_name: AnyStr = None
    public_ip: AnyStr = None
    private_ip: AnyStr = None
    sys_name: AnyStr = None
