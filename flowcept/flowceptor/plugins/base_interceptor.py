from abc import ABCMeta, abstractmethod
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
)

from flowcept.commons.mq_dao import MQDao
from flowcept.flowceptor.plugins.settings_factory import get_settings


class BaseInterceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.settings = get_settings(plugin_key)
        self._mq_dao = MQDao()

    @abstractmethod
    def intercept(self, message: dict):
        """
        Method that intercepts the identified data
        :param message:
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def observe(self):
        raise NotImplementedError()

    @abstractmethod
    def callback(self, *args, **kwargs):
        """
        Method that decides what do to when a change is identified.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        raise NotImplementedError()

    @staticmethod
    def enrich_flowcept_message(intercepted_message: dict):
        intercepted_message["user"] = FLOWCEPT_USER
        intercepted_message["sys_name"] = SYS_NAME
        intercepted_message["node_name"] = NODE_NAME
        intercepted_message["login_name"] = LOGIN_NAME
        intercepted_message["public_ip"] = PUBLIC_IP
        intercepted_message["private_ip"] = PRIVATE_IP

    def post_intercept(self, intercepted_message: dict):
        flowcept_message = dict()
        flowcept_message["intercepted_message"] = intercepted_message
        flowcept_message["plugin_key"] = self.settings.key
        flowcept_message["msg_id"] = str(uuid4())
        now = datetime.utcnow()
        flowcept_message["utc_now_timestamp"] = now.timestamp()

        BaseInterceptor.enrich_flowcept_message(flowcept_message)

        print(
            f"Going to send to Redis an intercepted message:"
            f"\n\t{json.dumps(flowcept_message)}"
        )
        self._mq_dao.publish(json.dumps(flowcept_message))
