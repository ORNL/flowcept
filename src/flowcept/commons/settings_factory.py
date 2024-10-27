"""Settings module."""

from flowcept.commons.vocabulary import Vocabulary
from flowcept.configs import settings

from flowcept.commons.flowcept_dataclasses.base_settings_dataclasses import (
    BaseSettings,
    KeyValue,
)
from flowcept.flowceptor.adapters.zambeze.zambeze_dataclasses import (
    ZambezeSettings,
)
from flowcept.flowceptor.adapters.mlflow.mlflow_dataclasses import (
    MLFlowSettings,
)
from flowcept.flowceptor.adapters.tensorboard.tensorboard_dataclasses import (
    TensorboardSettings,
)
from flowcept.flowceptor.adapters.dask.dask_dataclasses import (
    DaskSettings,
)


SETTINGS_CLASSES = {
    Vocabulary.Settings.ZAMBEZE_KIND: ZambezeSettings,
    Vocabulary.Settings.MLFLOW_KIND: MLFlowSettings,
    Vocabulary.Settings.TENSORBOARD_KIND: TensorboardSettings,
    Vocabulary.Settings.DASK_KIND: DaskSettings,
}


def _build_base_settings(kind: str, settings_dict: dict) -> BaseSettings:
    settings_obj = SETTINGS_CLASSES[kind](**settings_dict)
    return settings_obj


def get_settings(adapter_key: str) -> BaseSettings:
    """Get the settings."""
    if adapter_key is None:  # TODO: :base-interceptor-refactor:
        return None
    settings_dict = settings[Vocabulary.Settings.ADAPTERS][adapter_key]
    if not settings_dict:
        raise Exception(
            f"You must specify the adapter <<{adapter_key}>> in" f" the settings YAML file."
        )
    settings_dict["key"] = adapter_key
    kind = settings_dict[Vocabulary.Settings.KIND]
    settings_obj = _build_base_settings(kind, settings_dict)

    # Add any specific setting builder below
    if kind == Vocabulary.Settings.ZAMBEZE_KIND:
        if settings_obj.key_values_to_filter is not None:
            settings_obj.key_values_to_filter = [
                KeyValue(**item) for item in settings_obj.key_values_to_filter
            ]
    return settings_obj
