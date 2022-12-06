from abc import ABCMeta, abstractmethod
import json
from datetime import datetime
from uuid import uuid4
from redis import Redis

from flowcept.configs import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
)

from flowcept.flowceptor.plugins.settings_factory import get_settings


class BaseInterceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.settings = get_settings(plugin_key)
        self._redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

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

    def post_intercept(self, intercepted_message: dict):
        intercepted_message["plugin_key"] = self.settings.key
        if "msg_id" not in intercepted_message:
            intercepted_message["msg_id"] = str(uuid4())
        if "time" not in intercepted_message:
            now = datetime.now()
            dt_string = now.strftime("%d/%m/%Y %H:%M:%S")
            intercepted_message["time"] = dt_string
        print(
            f"Going to send to Redis an intercepted message:"
            f"\n\t{json.dumps(intercepted_message)}"
        )
        self._redis.publish(REDIS_CHANNEL, json.dumps(intercepted_message))
