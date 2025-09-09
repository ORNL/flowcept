"""Flowcept package."""

from flowcept.version import __version__


def __getattr__(name):
    if name == "Flowcept":
        from flowcept.flowcept_api.flowcept_controller import Flowcept

        return Flowcept

    elif name == "WorkflowObject":
        from flowcept.commons.flowcept_dataclasses.workflow_object import (
            WorkflowObject,
        )

        return WorkflowObject

    elif name == "TaskObject":
        from flowcept.commons.flowcept_dataclasses.task_object import TaskObject

        return TaskObject

    elif name == "flowcept_task":
        from flowcept.instrumentation.flowcept_task import flowcept_task

        return flowcept_task

    elif name == "FlowceptTask":
        from flowcept.instrumentation.task_capture import FlowceptTask

        return FlowceptTask

    elif name == "flowcept_torch":
        from flowcept.instrumentation.flowcept_torch import flowcept_torch

        return flowcept_torch

    elif name == "FlowceptLoop":
        from flowcept.instrumentation.flowcept_loop import FlowceptLoop

        return FlowceptLoop

    elif name == "telemetry_flowcept_task":
        from flowcept.instrumentation.flowcept_task import telemetry_flowcept_task

        return telemetry_flowcept_task

    elif name == "lightweight_flowcept_task":
        from flowcept.instrumentation.flowcept_task import lightweight_flowcept_task

        return lightweight_flowcept_task

    elif name == "FlowceptDaskWorkerAdapter":
        from flowcept.flowceptor.adapters.dask.dask_plugins import (
            FlowceptDaskWorkerAdapter,
        )

        return FlowceptDaskWorkerAdapter

    elif name == "SETTINGS_PATH":
        from configs import SETTINGS_PATH

        return SETTINGS_PATH
    elif name == "TaskQueryAPI":
        from flowcept.flowcept_api.task_query_api import TaskQueryAPI

        return TaskQueryAPI
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "FlowceptDaskWorkerAdapter",
    "TaskQueryAPI",
    "flowcept_task",
    "FlowceptLoop",
    "FlowceptTask",
    "telemetry_flowcept_task",
    "lightweight_flowcept_task",
    "Flowcept",
    "flowcept_torch",
    "WorkflowObject",
    "__version__",
    "SETTINGS_PATH",
]
