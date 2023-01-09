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
from flowcept.flowceptor.plugins.dask.dask_dataclasses import (
    DaskSettings,
)


SETTINGS_CLASSES = {
    Vocabulary.Settings.ZAMBEZE_KIND: ZambezeSettings,
    Vocabulary.Settings.MLFLOW_KIND: MLFlowSettings,
    Vocabulary.Settings.TENSORBOARD_KIND: TensorboardSettings,
    Vocabulary.Settings.DASK_KIND: DaskSettings,
}


def _build_base_settings(kind, settings) -> BaseSettings:

    settings_obj = SETTINGS_CLASSES.get(kind)(**settings)
    if hasattr(settings_obj, "file_path") and not os.path.isabs(
        settings_obj.file_path
    ):
        settings_obj.file_path = os.path.join(
            PROJECT_DIR_PATH, settings_obj.file_path
        )
    return settings_obj


def get_settings(plugin_key: str) -> BaseSettings:
    # TODO: use the factory pattern
    with open(SETTINGS_PATH) as f:
        data = yaml.load(f, Loader=yaml.FullLoader)
    settings = data[Vocabulary.Settings.PLUGINS].get(plugin_key)
    if not settings:
        raise Exception(
            f"You must specify the plugin <<{plugin_key}>> in the settings YAML file."
        )
    settings["key"] = plugin_key
    kind = settings[Vocabulary.Settings.KIND]
    settings_obj = _build_base_settings(kind, settings)

    # Add any specific setting builder below
    if kind == Vocabulary.Settings.ZAMBEZE_KIND:
        settings_obj.key_values_to_filter = [
            KeyValue(**item) for item in settings_obj.key_values_to_filter
        ]
    return settings_obj
