import os
import yaml

from flowcept.commons.vocabulary import Vocabulary
from flowcept.configs import (
    PROJECT_DIR_PATH,
    SETTINGS_PATH,
)

from flowcept.flowceptor.plugins.base_settings_dataclasses import (
    BaseSettings,
    KeyValue,
)
from flowcept.flowceptor.plugins.zambeze.zambeze_dataclasses import (
    ZambezeSettings,
)
from flowcept.flowceptor.plugins.mlflow.mlflow_dataclasses import (
    MLFlowSettings,
)
from flowcept.flowceptor.plugins.tensorboard.tensorboard_dataclasses import (
    TensorboardSettings,
)


def get_settings(plugin_key: str) -> BaseSettings:
    # TODO: use the factory pattern
    with open(SETTINGS_PATH) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    settings = data[Vocabulary.Settings.PLUGINS][plugin_key]
    settings["key"] = plugin_key
    settings_obj: BaseSettings = None
    if settings[Vocabulary.Settings.KIND] == Vocabulary.Settings.ZAMBEZE_KIND:
        settings_obj: ZambezeSettings = ZambezeSettings(**settings)
        settings_obj.key_values_to_filter = [
            KeyValue(**item) for item in settings_obj.key_values_to_filter
        ]
    elif (
        settings[Vocabulary.Settings.KIND] == Vocabulary.Settings.MLFLOW_KIND
    ):
        settings_obj: MLFlowSettings = MLFlowSettings(**settings)
        if not os.path.isabs(settings_obj.file_path):
            settings_obj.file_path = os.path.join(
                PROJECT_DIR_PATH, settings_obj.file_path
            )
    elif (
        settings[Vocabulary.Settings.KIND]
        == Vocabulary.Settings.TENSORBOARD_KIND
    ):
        settings_obj: TensorboardSettings = TensorboardSettings(**settings)
        if not os.path.isabs(settings_obj.file_path):
            settings_obj.file_path = os.path.join(
                PROJECT_DIR_PATH, settings_obj.file_path
            )
    return settings_obj
