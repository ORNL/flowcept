import uuid
from time import time

import flowcept.commons
from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
    Status,
)

from flowcept.instrumentation.decorators import instrumentation_interceptor
from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import REPLACE_NON_JSON_SERIALIZABLE
from functools import wraps


# TODO: :code-reorg: consider moving it to utils and reusing it in dask interceptor
def default_args_handler(task_message, *args, **kwargs):
    args_handled = {}
    if args is not None and len(args):
        for i in range(len(args)):
            args_handled[f"arg_{i}"] = args[i]
    if kwargs is not None and len(kwargs):
        task_message.workflow_id = kwargs.pop("workflow_id", None)
        args_handled.update(kwargs)
    if REPLACE_NON_JSON_SERIALIZABLE:
        args_handled = replace_non_serializable(args_handled)
    return args_handled


def flowcept_task(func=None, **decorator_kwargs):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_obj = TaskObject()
            task_obj.activity_id = func.__name__
            task_obj.task_id = str(uuid.uuid4())

            args_handler = decorator_kwargs.get(
                "args_handler", default_args_handler
            )

            task_obj.telemetry_at_start = (
                instrumentation_interceptor.telemetry_capture.capture()
            )
            task_obj.started_at = time()
            task_obj.used = args_handler(task_obj, *args, **kwargs)
            try:
                result = func(*args, **kwargs)
                task_obj.status = Status.FINISHED
            except Exception as e:
                task_obj.status = Status.ERROR
                result = None
                task_obj.stderr = str(e)
            task_obj.ended_at = time()
            task_obj.telemetry_at_end = (
                instrumentation_interceptor.telemetry_capture.capture()
            )
            try:
                if isinstance(result, dict):
                    task_obj.generated = args_handler(task_obj, **result)
                else:
                    task_obj.generated = args_handler(task_obj, result)
            except Exception as e:
                flowcept.commons.logger.exception(e)

            instrumentation_interceptor.intercept(task_obj)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)
