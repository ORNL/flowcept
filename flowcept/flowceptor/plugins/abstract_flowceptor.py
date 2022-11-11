from abc import ABCMeta, abstractmethod
import os
import json
import yaml
import redis

from flowcept.commons.vocabulary import Vocabulary
from flowcept.configs import (
    PROJECT_DIR_PATH,
    SETTINGS_PATH,
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
)
from flowcept.flowceptor.plugins.settings_data_classes import (
    ZambezeSettings,
    KeyValuesToFilter,
    MLFlowSettings,
)


class AbstractFlowceptor(object, metaclass=ABCMeta):
    def __init__(self, plugin_key):
        self.settings = AbstractFlowceptor.__get_settings(plugin_key)
        self._redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

    @staticmethod
    def __get_settings(plugin_key):
        # TODO: use factory pattern
        with open(SETTINGS_PATH) as f:
            data = yaml.load(f, Loader=yaml.FullLoader)
        settings = data[Vocabulary.Settings.PLUGINS][plugin_key]
        if settings[Vocabulary.Settings.KIND]\
                == Vocabulary.Settings.ZAMBEZE_KIND:
            settings_obj: ZambezeSettings = ZambezeSettings(**settings)
            settings_obj.key_values_to_filter = [
                KeyValuesToFilter(**item)
                for item in settings_obj.key_values_to_filter
            ]
            return settings_obj
        elif settings[Vocabulary.Settings.KIND]\
                == Vocabulary.Settings.MLFLOW_KIND:
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

    def post_intercept(self, intercepted_message: dict):
        print(
            f"Going to send to Redis an intercepted message:"
            f"\n\t{json.dumps(intercepted_message)}"
        )
        self._redis.publish(REDIS_CHANNEL, json.dumps(intercepted_message))
