from flowcept.configs import PROJECT_NAME, ADAPTERS, SETTINGS_PATH
from flowcept.version import __version__
from flowcept.commons.vocabulary import Vocabulary

from flowcept.flowcept_api.consumer_api import FlowceptConsumerAPI
from flowcept.flowcept_api.task_query_api import TaskQueryAPI

from flowcept.flowcept_api import db_api

try:
    from flowcept.flowceptor.decorators.responsible_ai import (
        model_explainer,
        model_profiler,
    )
except:
    pass

from flowcept.commons.flowcept_logger import FlowceptLogger

logger = FlowceptLogger().get_logger()


def get_adapter_exception_msg(adapter_kind):
    return (
        f"You have an adapter for {adapter_kind} in"
        f" {SETTINGS_PATH} but we couldn't import its interceptor. "
        f" Consider fixing the following exception or remove that adapter "
        f" from the settings."
        f" Exception:"
    )


if Vocabulary.Settings.ZAMBEZE_KIND in ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.zambeze.zambeze_interceptor import (
            ZambezeInterceptor,
        )
    except Exception as e:
        logger.error(
            get_adapter_exception_msg(Vocabulary.Settings.ZAMBEZE_KIND)
        )
        logger.exception(e)

if Vocabulary.Settings.TENSORBOARD_KIND in ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.tensorboard.tensorboard_interceptor import (
            TensorboardInterceptor,
        )
    except Exception as e:
        logger.error(
            get_adapter_exception_msg(Vocabulary.Settings.TENSORBOARD_KIND)
        )
        logger.exception(e)

if Vocabulary.Settings.MLFLOW_KIND in ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.mlflow.mlflow_interceptor import (
            MLFlowInterceptor,
        )
    except Exception as e:
        logger.error(
            get_adapter_exception_msg(Vocabulary.Settings.MLFLOW_KIND)
        )
        logger.exception(e)

if Vocabulary.Settings.DASK_KIND in ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.dask.dask_plugins import (
            FlowceptDaskSchedulerAdapter,
            FlowceptDaskWorkerAdapter,
        )
    except Exception as e:
        logger.error(get_adapter_exception_msg(Vocabulary.Settings.DASK_KIND))
        logger.exception(e)
