"""Task module."""

from time import time
from functools import wraps
import flowcept.commons
from flowcept import Flowcept
from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
    Status,
)

from flowcept.instrumentation.decorators import instrumentation_interceptor
from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import (
    REPLACE_NON_JSON_SERIALIZABLE,
    INSTRUMENTATION_ENABLED,
)


# TODO: :code-reorg: consider moving it to utils and reusing it in dask interceptor
def default_args_handler(task_message: TaskObject, *args, **kwargs):
    """Get default arguments."""
    args_handled = {}
    if args is not None and len(args):
        for i in range(len(args)):
            args_handled[f"arg_{i}"] = args[i]
    if kwargs is not None and len(kwargs):
        task_message.workflow_id = task_message.workflow_id or kwargs.pop("workflow_id", None)
        args_handled.update(kwargs)
    task_message.workflow_id = task_message.workflow_id or Flowcept.current_workflow_id
    if REPLACE_NON_JSON_SERIALIZABLE:
        args_handled = replace_non_serializable(args_handled)
    return args_handled


def telemetry_flowcept_task(func=None):
    """Get telemetry task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_obj = {}
            task_obj["type"] = "task"
            task_obj["started_at"] = time()
            task_obj["activity_id"] = func.__qualname__
            task_obj["task_id"] = str(id(task_obj))
            task_obj["workflow_id"] = kwargs.pop("workflow_id")
            task_obj["used"] = kwargs
            tel = instrumentation_interceptor.telemetry_capture.capture()
            if tel is not None:
                task_obj["telemetry_at_start"] = tel.to_dict()
            try:
                result = func(*args, **kwargs)
                task_obj["status"] = Status.FINISHED.value
            except Exception as e:
                task_obj["status"] = Status.ERROR.value
                result = None
                task_obj["stderr"] = str(e)
            # task_obj["ended_at"] = time()
            tel = instrumentation_interceptor.telemetry_capture.capture()
            if tel is not None:
                task_obj["telemetry_at_end"] = tel.to_dict()
            task_obj["generated"] = result
            instrumentation_interceptor.intercept(task_obj)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def lightweight_flowcept_task(func=None):
    """Get lightweight task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # t0 = time()
            # task_obj["started_at"] = time()
            # task_obj["type"] = "task"

            # task_obj["task_id"] = t0

            # task_obj["used"] = kwargs
            result = func(*args, **kwargs)
            # try:
            #     task_obj["status"] = Status.FINISHED.value
            # except Exception as e:
            #     task_obj["status"] = Status.ERROR.value
            #     result = None
            #     task_obj["stderr"] = str(e)
            # task_obj["ended_at"] = time()
            # generatedKV = task_obj_pb2.GeneratedKV(key="y", val=result["y"])
            # task_obj = task_obj_pb2.TaskObject(type="task",
            #                                    workflow_id=kwargs.pop(
            #                                        "workflow_id"),
            #                                    activity_id=func.__name__,
            #                                    y=result["y"]
            #                                    )

            task_dict = dict(
                type="task",
                # workflow_id=kwargs.pop("workflow_id", None),
                activity_id=func.__name__,
                used=kwargs,
                generated=result,
            )
            instrumentation_interceptor.intercept(task_dict)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def flowcept_task(func=None, **decorator_kwargs):
    """Get flowcept task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not INSTRUMENTATION_ENABLED:
                return func(*args, **kwargs)

            args_handler = decorator_kwargs.get("args_handler", default_args_handler)
            task_obj = TaskObject()

            task_obj.activity_id = func.__name__
            task_obj.used = args_handler(task_obj, *args, **kwargs)
            task_obj.started_at = time()
            task_obj.task_id = str(task_obj.started_at)
            task_obj.telemetry_at_start = instrumentation_interceptor.telemetry_capture.capture()
            try:
                result = func(*args, **kwargs)
                task_obj.status = Status.FINISHED
            except Exception as e:
                task_obj.status = Status.ERROR
                result = None
                task_obj.stderr = str(e)
            task_obj.ended_at = time()
            task_obj.telemetry_at_end = instrumentation_interceptor.telemetry_capture.capture()
            try:
                if isinstance(result, dict):
                    task_obj.generated = args_handler(task_obj, **result)
                else:
                    task_obj.generated = args_handler(task_obj, result)
            except Exception as e:
                flowcept.commons.logger.exception(e)

            instrumentation_interceptor.intercept(task_obj.to_dict())
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)
