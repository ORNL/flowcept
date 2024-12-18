"""Flowcept package."""

from flowcept.configs import SETTINGS_PATH
from flowcept.version import __version__

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)


def __getattr__(name):
    if name == "Flowcept":
        from flowcept.flowcept_api.flowcept_controller import Flowcept

        return Flowcept

    elif name == "flowcept_task":
        from flowcept.instrumentation.flowcept_task import flowcept_task

        return flowcept_task

    elif name == "flowcept_torch":
        from flowcept.instrumentation.flowcept_torch import flowcept_torch

        return flowcept_torch

    elif name == "FlowceptLoop":
        from flowcept.instrumentation.flowcept_loop import FlowceptLoop

        return FlowceptLoop

    elif name == "telemetry_flowcept_task":
        from flowcept.instrumentation.flowcept_task import telemetry_flowcept_task

        return telemetry_flowcept_task

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
    "flowcept_task",
    "FlowceptLoop",
    "telemetry_flowcept_task",
    "Flowcept",
    "flowcept_torch",
    "WorkflowObject",
    "__version__",
    "SETTINGS_PATH",
]
