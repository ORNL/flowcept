from abc import ABCMeta, abstractmethod

from flowcept.commons.utils import get_utc_now
from flowcept.configs import (
    FLOWCEPT_USER,
    SYS_NAME,
    NODE_NAME,
    LOGIN_NAME,
    PUBLIC_IP,
    PRIVATE_IP,
    CAMPAIGN_ID,
    HOSTNAME,
    EXTRA_METADATA,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao import MQDao
from flowcept.commons.flowcept_dataclasses.task_message import TaskMessage
from flowcept.flowceptor.plugins.settings_factory import get_settings

from flowcept.flowceptor.telemetry_capture import TelemetryCapture

from flowcept.version import __version__


def _enrich_task_message(settings_key, task_msg: TaskMessage):
    if task_msg.utc_timestamp is None:
        task_msg.utc_timestamp = get_utc_now()

    if task_msg.adapter_id is None:
        task_msg.adapter_id = settings_key

    if task_msg.user is None:
        task_msg.user = FLOWCEPT_USER

    if task_msg.campaign_id is None:
        task_msg.campaign_id = CAMPAIGN_ID

    if task_msg.sys_name is None:
        task_msg.sys_name = SYS_NAME

    if task_msg.node_name is None:
        task_msg.node_name = NODE_NAME

    if task_msg.login_name is None:
        task_msg.login_name = LOGIN_NAME

    if task_msg.public_ip is None and PUBLIC_IP is not None:
        task_msg.public_ip = PUBLIC_IP

    if task_msg.private_ip is None and PRIVATE_IP is not None:
        task_msg.private_ip = PRIVATE_IP

    if task_msg.hostname is None and HOSTNAME is not None:
        task_msg.hostname = HOSTNAME

    if task_msg.extra_metadata is None and EXTRA_METADATA is not None:
        task_msg.extra_metadata = EXTRA_METADATA

    if task_msg.flowcept_version is None:
        task_msg.flowcept_version = __version__


class BaseInterceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.logger = FlowceptLogger().get_logger()
        self.settings = get_settings(plugin_key)
        self._mq_dao = MQDao()
        self.telemetry_capture = TelemetryCapture()

    def prepare_task_msg(self, *args, **kwargs) -> TaskMessage:
        raise NotImplementedError()

    def start(self) -> "BaseInterceptor":
        """
        Starts an interceptor
        :return:
        """
        self._mq_dao.start_time_based_flushing()
        self.telemetry_capture.init_gpu_telemetry()
        return self

    def stop(self) -> bool:
        """
        Gracefully stops an interceptor
        :return:
        """
        self._mq_dao.stop()
        self.telemetry_capture.shutdown_gpu_telemetry()

    def observe(self, *args, **kwargs):
        """
        This method implements data observability over a data channel
         (e.g., a file, a DBMS, an MQ)
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def callback(self, *args, **kwargs):
        """
        Method that implements the logic that decides what do to when a change
         (e.g., task state change) is identified.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        raise NotImplementedError()

    def intercept(self, task_msg: TaskMessage):
        if self.settings.enrich_messages:
            _enrich_task_message(self.settings.key, task_msg)

        _msg = task_msg.to_dict()
        self.logger.debug(
            f"Going to send to Redis an intercepted message:"
            f"\n\t[BEGIN_MSG]{_msg}\n[END_MSG]\t"
        )
        self._mq_dao.publish(_msg)
