"""Main driver module."""

import sys

from flowcept import (
    Flowcept,
    ZambezeInterceptor,
    MLFlowInterceptor,
    TensorboardInterceptor,
)
from flowcept.commons.vocabulary import Vocabulary
from flowcept.configs import settings


INTERCEPTORS = {
    Vocabulary.Settings.ZAMBEZE_KIND: ZambezeInterceptor,
    Vocabulary.Settings.MLFLOW_KIND: MLFlowInterceptor,
    Vocabulary.Settings.TENSORBOARD_KIND: TensorboardInterceptor,
    # Vocabulary.Settings.DASK_KIND: DaskInterceptor,
}


def main():
    """Run the main driver."""
    interceptors = []
    for plugin_key in settings["plugins"]:
        plugin_settings_obj = settings["plugins"][plugin_key]
        if "enabled" in plugin_settings_obj and not plugin_settings_obj["enabled"]:
            continue

        kind = plugin_settings_obj["kind"]

        if kind in INTERCEPTORS:
            interceptor = INTERCEPTORS[plugin_settings_obj["kind"]](plugin_key)
            interceptors.append(interceptor)

    consumer = Flowcept(interceptors)
    consumer.start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
