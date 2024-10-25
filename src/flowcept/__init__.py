"""Flowcept package."""

import flowcept

from flowcept.configs import SETTINGS_PATH

from flowcept.version import __version__

from flowcept.commons.vocabulary import Vocabulary


from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowcept_api.task_query_api import TaskQueryAPI
from flowcept.instrumentation.decorators.flowcept_task import flowcept_task

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)

# These resp_ai imports below are adding long wait in flowcept imports!
# try:
#     from flowcept.instrumentation.decorators.responsible_ai import (
#         #model_explainer,
#         #model_profiler,
#     )
# except:
#     pass

if Vocabulary.Settings.ZAMBEZE_KIND in flowcept.configs.ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.zambeze.zambeze_interceptor import (
            ZambezeInterceptor,
        )
    except Exception as _exp:
        flowcept.commons.logger.error(
            flowcept.commons.get_adapter_exception_msg(Vocabulary.Settings.ZAMBEZE_KIND)
        )
        flowcept.commons.logger.exception(_exp)

if Vocabulary.Settings.TENSORBOARD_KIND in flowcept.configs.ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.tensorboard.tensorboard_interceptor import (
            TensorboardInterceptor,
        )
    except Exception as _exp:
        flowcept.commons.logger.error(
            flowcept.commons.get_adapter_exception_msg(Vocabulary.Settings.TENSORBOARD_KIND)
        )
        flowcept.commons.logger.exception(_exp)

if Vocabulary.Settings.MLFLOW_KIND in flowcept.configs.ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.mlflow.mlflow_interceptor import (
            MLFlowInterceptor,
        )
    except Exception as _exp:
        flowcept.commons.logger.error(
            flowcept.commons.get_adapter_exception_msg(Vocabulary.Settings.MLFLOW_KIND)
        )
        flowcept.commons.logger.exception(_exp)

if Vocabulary.Settings.DASK_KIND in flowcept.configs.ADAPTERS:
    try:
        from flowcept.flowceptor.adapters.dask.dask_plugins import (
            FlowceptDaskSchedulerAdapter,
            FlowceptDaskWorkerAdapter,
        )
    except Exception as _exp:
        flowcept.commons.get_adapter_exception_msg(Vocabulary.Settings.DASK_KIND)
        flowcept.commons.logger.exception(_exp)

__all__ = [
    "FlowceptDaskWorkerAdapter",
    "FlowceptDaskSchedulerAdapter",
    "MLFlowInterceptor",
    "TensorboardInterceptor",
    "ZambezeInterceptor",
    "WorkflowObject",
    "flowcept_task",
    "TaskQueryAPI",
    "Flowcept",
    "__version__",
    "SETTINGS_PATH",
]
