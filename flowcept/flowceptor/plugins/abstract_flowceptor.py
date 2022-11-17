from abc import ABCMeta, abstractmethod
import os
import json
import yaml
from redis import Redis

from flowcept.commons.vocabulary import Vocabulary
from flowcept.configs import (
    PROJECT_DIR_PATH,
    SETTINGS_PATH,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
)
from flowcept.flowceptor.plugins.settings_dataclasses import (
    ZambezeSettings,
    KeyValue,
    MLFlowSettings,
    AbstractSettings,
)


class AbstractFlowceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.plugin_key = plugin_key
        self.settings = AbstractFlowceptor.get_settings(self.plugin_key)
        self._redis = Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    @staticmethod
    def get_settings(plugin_key: str) -> AbstractSettings:
        # TODO: use the factory pattern
        with open(SETTINGS_PATH) as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        settings = data[Vocabulary.Settings.PLUGINS][plugin_key]
        if (
            settings[Vocabulary.Settings.KIND]
            == Vocabulary.Settings.ZAMBEZE_KIND
        ):
            settings_obj: ZambezeSettings = ZambezeSettings(**settings)
            settings_obj.key_values_to_filter = [
                KeyValue(**item) for item in settings_obj.key_values_to_filter
            ]
            return settings_obj
        elif (
            settings[Vocabulary.Settings.KIND]
            == Vocabulary.Settings.MLFLOW_KIND
        ):
            settings_obj: MLFlowSettings = MLFlowSettings(**settings)
            if not os.path.isabs(settings_obj.file_path):
                settings_obj.file_path = os.path.join(
                    PROJECT_DIR_PATH, settings_obj.file_path
                )
            return settings_obj

    @abstractmethod
    def intercept(self, message: dict):
        raise NotImplementedError()

    @abstractmethod
    def observe(self):
        raise NotImplementedError()

    @abstractmethod
    def callback(self, *args, **kwargs):
        raise NotImplementedError()

    def post_intercept(self, intercepted_message: dict):
        print(
            f"Going to send to Redis an intercepted message:"
            f"\n\t{json.dumps(intercepted_message)}"
        )
        self._redis.publish(REDIS_CHANNEL, json.dumps(intercepted_message))
