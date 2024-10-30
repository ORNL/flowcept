"""Flowcept package."""

from flowcept.configs import SETTINGS_PATH
from flowcept.version import __version__
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.instrumentation.decorators.flowcept_task import flowcept_task

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)


def __getattr__(name):
    if name == "MLFlowInterceptor":
        from flowcept.flowceptor.adapters.mlflow.mlflow_interceptor import (
            MLFlowInterceptor,
        )

        return MLFlowInterceptor
    elif name == "FlowceptDaskSchedulerAdapter":
        from flowcept.flowceptor.adapters.dask.dask_plugins import (
            FlowceptDaskSchedulerAdapter,
        )

        return FlowceptDaskSchedulerAdapter
    elif name == "FlowceptDaskWorkerAdapter":
        from flowcept.flowceptor.adapters.dask.dask_plugins import (
            FlowceptDaskWorkerAdapter,
        )

        return FlowceptDaskWorkerAdapter
    elif name == "TensorboardInterceptor":
        from flowcept.flowceptor.adapters.tensorboard.tensorboard_interceptor import (
            TensorboardInterceptor,
        )

        return TensorboardInterceptor
    elif name == "ZambezeInterceptor":
        from flowcept.flowceptor.adapters.zambeze.zambeze_interceptor import (
            ZambezeInterceptor,
        )

        return ZambezeInterceptor
    elif name == "TaskQueryAPI":
        from flowcept.flowcept_api.task_query_api import TaskQueryAPI

        return TaskQueryAPI
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "FlowceptDaskWorkerAdapter",
    "FlowceptDaskSchedulerAdapter",
    "MLFlowInterceptor",
    "TensorboardInterceptor",
    "ZambezeInterceptor",
    "TaskQueryAPI",
    "WorkflowObject",
    "flowcept_task",
    "Flowcept",
    "__version__",
    "SETTINGS_PATH",
]
