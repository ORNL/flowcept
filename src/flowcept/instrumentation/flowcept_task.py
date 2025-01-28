"""Task module."""

import threading
from time import time
from functools import wraps
import argparse
from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.commons.flowcept_logger import FlowceptLogger

from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import (
    REPLACE_NON_JSON_SERIALIZABLE,
    INSTRUMENTATION_ENABLED,
)
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor

_thread_local = threading.local()


# TODO: :code-reorg: consider moving it to utils and reusing it in dask interceptor
def default_args_handler(*args, **kwargs):
    """Get default arguments."""
    args_handled = {}
    if args is not None and len(args):
        if isinstance(args[0], argparse.Namespace):
            args_handled.update(args[0].__dict__)
            args = args[1:]
        for i in range(len(args)):
            args_handled[f"arg_{i}"] = args[i]
    if kwargs is not None and len(kwargs):
        args_handled.update(kwargs)
    if REPLACE_NON_JSON_SERIALIZABLE:
        args_handled = replace_non_serializable(args_handled)
    return args_handled


def telemetry_flowcept_task(func=None):
    """Get telemetry task."""
    if INSTRUMENTATION_ENABLED:
        interceptor = InstrumentationInterceptor.get_instance()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_obj = {}
            task_obj["type"] = "task"
            task_obj["started_at"] = time()
            task_obj["activity_id"] = func.__qualname__
            task_obj["task_id"] = str(task_obj["started_at"])
            _thread_local._flowcept_current_context_task_id = task_obj["task_id"]
            task_obj["workflow_id"] = kwargs.pop("workflow_id", Flowcept.current_workflow_id)
            task_obj["used"] = kwargs
            tel = interceptor.telemetry_capture.capture()
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
            tel = interceptor.telemetry_capture.capture()
            if tel is not None:
                task_obj["telemetry_at_end"] = tel.to_dict()
            task_obj["generated"] = result
            interceptor.intercept(task_obj)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def lightweight_flowcept_task(func=None):
    """Get lightweight task."""
    if INSTRUMENTATION_ENABLED:
        interceptor = InstrumentationInterceptor.get_instance()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            task_dict = dict(
                type="task",
                workflow_id=Flowcept.current_workflow_id,
                activity_id=func.__name__,
                used=kwargs,
                generated=result,
            )
            interceptor.intercept(task_dict)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


# def flowcept_task_switch(mode=None):
#     if mode is None:
#         return flowcept_task
#     elif mode == "disable":
#         return lambda _: _
#     else:
#         raise NotImplementedError


def flowcept_task(func=None, **decorator_kwargs):
    """Get flowcept task."""
    if INSTRUMENTATION_ENABLED:
        interceptor = InstrumentationInterceptor.get_instance()
        logger = FlowceptLogger()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not INSTRUMENTATION_ENABLED:
                return func(*args, **kwargs)

            args_handler = decorator_kwargs.get("args_handler", default_args_handler)
            task_obj = TaskObject()

            task_obj.activity_id = func.__name__
            handled_args = args_handler(*args, **kwargs)
            task_obj.workflow_id = handled_args.pop("workflow_id", Flowcept.current_workflow_id)
            task_obj.campaign_id = handled_args.pop("campaign_id", Flowcept.campaign_id)
            task_obj.used = handled_args
            task_obj.started_at = time()
            task_obj.task_id = str(task_obj.started_at)
            _thread_local._flowcept_current_context_task_id = task_obj.task_id
            task_obj.telemetry_at_start = interceptor.telemetry_capture.capture()
            try:
                result = func(*args, **kwargs)
                task_obj.status = Status.FINISHED
            except Exception as e:
                task_obj.status = Status.ERROR
                result = None
                logger.exception(e)
                task_obj.stderr = str(e)
            task_obj.ended_at = time()
            task_obj.telemetry_at_end = interceptor.telemetry_capture.capture()
            try:
                if result is not None:
                    if isinstance(result, dict):
                        task_obj.generated = args_handler(**result)
                    else:
                        task_obj.generated = args_handler(result)
            except Exception as e:
                logger.exception(e)

            interceptor.intercept(task_obj.to_dict())
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def get_current_context_task_id():
    """Retrieve the current task object from thread-local storage."""
    return getattr(_thread_local, "_flowcept_current_context_task_id", None)
