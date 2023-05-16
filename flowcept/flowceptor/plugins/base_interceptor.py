from abc import ABCMeta, abstractmethod
from datetime import datetime

from flowcept.commons.utils import get_utc_now
from flowcept.configs import (
    FLOWCEPT_USER,
    SYS_NAME,
    NODE_NAME,
    LOGIN_NAME,
    PUBLIC_IP,
    PRIVATE_IP,
    EXPERIMENT_ID,
    HOSTNAME,
    EXTRA_METADATA
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao import MQDao
from flowcept.commons.flowcept_data_classes import TaskMessage
from flowcept.flowceptor.plugins.settings_factory import get_settings


def _enrich_task_message(settings_key, task_msg: TaskMessage):
    if task_msg.utc_timestamp is None:
        task_msg.utc_timestamp = get_utc_now()

    if task_msg.plugin_id is None:
        task_msg.plugin_id = settings_key

    if task_msg.user is None:
        task_msg.user = FLOWCEPT_USER

    if task_msg.experiment_id is None:
        task_msg.experiment_id = EXPERIMENT_ID

    # if task_msg.msg_id is None:
    #     task_msg.msg_id = str(uuid4())

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


class BaseInterceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.logger = FlowceptLogger().get_logger()
        self.settings = get_settings(plugin_key)
        self._mq_dao = MQDao()

    def prepare_task_msg(self, *args, **kwargs) -> TaskMessage:
        raise NotImplementedError()

    def start(self) -> "BaseInterceptor":
        """
        Starts an interceptor
        :return:
        """
        raise NotImplementedError()

    def stop(self) -> bool:
        """
        Gracefully stops an interceptor
        :return:
        """
        self._mq_dao.stop()

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

        # dumped_task_msg = json.dumps(task_msg.__dict__)
        self.logger.debug(
            f"Going to send to Redis an intercepted message:"
            f"\n\t[BEGINMSG]{task_msg.__dict__}\n\t[ENDMSG]"
        )
        self._mq_dao.publish(task_msg.__dict__)
