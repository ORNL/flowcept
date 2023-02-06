from enum import Enum
from typing import Dict, AnyStr, Any, Union


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

    # def __init__(self,
    #     task_id: AnyStr = None,  # Any way to identify a task
    #     utc_timestamp: float = None,
    #     plugin_id: AnyStr = None,
    #     user: AnyStr = None,
    #     msg_id: AnyStr = None,  # TODO: Remove this from all plugins in the future
    #     used: Dict[AnyStr, Any] = None,  # Used parameter and files
    #     experiment_id: AnyStr = None,
    #     generated: Dict[AnyStr, Any] = None,  # Generated results and files
    #     start_time: float = None,
    #     end_time: float = None,
    #     workflow_id: AnyStr = None,
    #     activity_id: AnyStr = None,
    #     status: Status = None,
    #     stdout: Union[AnyStr, Dict] = None,
    #     stderr: Union[AnyStr, Dict] = None,
    #     custom_metadata: Dict[AnyStr, Any] = None,
    #     node_name: AnyStr = None,
    #     login_name: AnyStr = None,
    #     public_ip: AnyStr = None,
    #     private_ip: AnyStr = None,
    #     sys_name: AnyStr = None,
    #     address: AnyStr = None
    # ):
    #     self.task_id = task_id
    #     self.utc_timestamp = utc_timestamp
    #     self.plugin_id = plugin_id
    #     self.user = user
    #     self.msg_id = msg_id  # TODO: Remove this from all plugins in the future
    #     self.used = used  # Used parameter and files
    #     self.experiment_id = experiment_id
    #     self.generated = generated  # Generated results and files
    #     self.start_time = start_time
    #     self.end_time = end_time
    #     self.workflow_id = workflow_id
    #     self.activity_id = activity_id
    #     self.status = status
    #     self.stdout = stdout
    #     self.stderr = stderr
    #     self.custom_metadata = custom_metadata
    #     self.node_name = node_name
    #     self.login_name = login_name
    #     self.public_ip = public_ip
    #     self.private_ip = private_ip
    #     self.sys_name = sys_name
    #     self.address = address

    @staticmethod
    def get_dict_field_names():
        return ["used", "generated", "custom_metadata"]
