from abc import ABCMeta, abstractmethod
from typing import Dict
import json
from datetime import datetime
from uuid import uuid4

from flowcept.configs import (
    FLOWCEPT_USER,
    SYS_NAME,
    NODE_NAME,
    LOGIN_NAME,
    PUBLIC_IP,
    PRIVATE_IP,
    EXPERIMENT_ID,
)

from flowcept.commons.mq_dao import MQDao
from flowcept.commons.flowcept_data_classes import TaskMessage
from flowcept.flowceptor.plugins.settings_factory import get_settings


class BaseInterceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.settings = get_settings(plugin_key)
        self._mq_dao = MQDao()

    @abstractmethod
    def intercept(self, message: Dict):
        """
        Method that intercepts the identified data
        :param message:
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def observe(self):
        """
        This method implements data observability over a data channel (e.g., a file, a DBMS, an MQ)
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def callback(self, *args, **kwargs):
        """
        Method that implements the logic that decides what do to when a change (e.g., task state change) is identified.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        raise NotImplementedError()

    def enrich_task_message(self, task_msg: TaskMessage):
        now = datetime.utcnow()
        task_msg.utc_timestamp = now.timestamp()
        task_msg.plugin_id = self.settings.key
        task_msg.user = FLOWCEPT_USER
        task_msg.experiment_id = EXPERIMENT_ID
        task_msg.msg_id = str(uuid4())

        task_msg.sys_name = SYS_NAME
        task_msg.node_name = NODE_NAME
        task_msg.login_name = LOGIN_NAME
        task_msg.public_ip = PUBLIC_IP
        task_msg.private_ip = PRIVATE_IP

    def prepare_and_send(self, intercepted_message: Dict):

        task_msg = TaskMessage()
        task_msg.task_id = intercepted_message.get("task_id")
        if intercepted_message.get("used"):
            task_msg.used = intercepted_message.get("used")
        if intercepted_message.get("generated"):
            task_msg.generated = intercepted_message.get("generated")
        if intercepted_message.get("start_time"):
            task_msg.start_time = intercepted_message.get("start_time")
        if intercepted_message.get("end_time"):
            task_msg.end_time = intercepted_message.get("end_time")
        if intercepted_message.get("activity_id"):
            task_msg.activity_id = intercepted_message.get("activity_id")
        if intercepted_message.get("status"):
            task_msg.status = intercepted_message.get("status")
        if intercepted_message.get("stdout"):
            task_msg.stdout = intercepted_message.get("stdout")
        if intercepted_message.get("stderr"):
            task_msg.stderr = intercepted_message.get("stderr")
        if intercepted_message.get("custom_metadata"):
            task_msg.custom_metadata = intercepted_message.get(
                "custom_metadata"
            )

        self.enrich_task_message(task_msg)

        dumped_task_msg = json.dumps(task_msg.__dict__)
        print(
            f"Going to send to Redis an intercepted message:"
            f"\n\t{dumped_task_msg}"
        )
        self._mq_dao.publish(dumped_task_msg)
