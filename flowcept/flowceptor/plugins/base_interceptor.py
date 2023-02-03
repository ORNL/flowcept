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
    def intercept(self, message: TaskMessage):
        """
        Method that intercepts the identified data
        :param message:
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def observe(self):
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

    def enrich_task_message(self, task_msg: TaskMessage):
        if task_msg.utc_timestamp is None:
            now = datetime.utcnow()
            task_msg.utc_timestamp = now.timestamp()

        if task_msg.plugin_id is None:
            task_msg.plugin_id = self.settings.key

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

        if task_msg.public_ip is None:
            task_msg.public_ip = PUBLIC_IP

        if task_msg.private_ip is None:
            task_msg.private_ip = PRIVATE_IP

    # @abstractmethod
    # def prepare_task_message(self, original_msg) -> TaskMessage:
    #     raise NotImplementedError()

    def prepare_and_send(self, intercepted_message: TaskMessage):

        # task_msg = TaskMessage()
        # task_msg.task_id = intercepted_message.get("task_id")
        # if intercepted_message.get("used"):
        #     task_msg.used = intercepted_message.get("used")
        # if intercepted_message.get("generated"):
        #     task_msg.generated = intercepted_message.get("generated")
        # if intercepted_message.get("start_time"):
        #     task_msg.start_time = intercepted_message.get("start_time")
        # if intercepted_message.get("end_time"):
        #     task_msg.end_time = intercepted_message.get("end_time")
        # if intercepted_message.get("activity_id"):
        #     task_msg.activity_id = intercepted_message.get("activity_id")
        # if intercepted_message.get("status"):
        #     task_msg.status = intercepted_message.get("status")
        # if intercepted_message.get("stdout"):
        #     task_msg.stdout = intercepted_message.get("stdout")
        # if intercepted_message.get("stderr"):
        #     task_msg.stderr = intercepted_message.get("stderr")
        # if intercepted_message.get("custom_metadata"):
        #     task_msg.custom_metadata = intercepted_message.get(
        #         "custom_metadata"
        #     )

        if self.settings.enrich_messages:
            self.enrich_task_message(intercepted_message)

        # Converting any arg to kwarg in the form {"arg1": val1, "arg2: val2}
        for field in TaskMessage.get_dict_field_names():
            field_val = getattr(intercepted_message, field)
            if field_val is not None and type(field_val) != dict:
                field_val_dict = {}

                if type(field_val) == list:
                    i = 0
                    for arg in field_val:
                        field_val_dict[f"arg{i}"] = arg
                        i += 1
                else:  # Scalar value
                    field_val_dict["arg1"] = field_val
                setattr(intercepted_message, field, field_val_dict)

        dumped_task_msg = json.dumps(intercepted_message.__dict__)
        print(
            f"Going to send to Redis an intercepted message:"
            f"\n\t{dumped_task_msg}"
        )
        self._mq_dao.publish(dumped_task_msg)
