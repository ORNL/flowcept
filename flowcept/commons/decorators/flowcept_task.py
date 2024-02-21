import uuid
from time import time

import torch

import flowcept.commons
from flowcept.commons.flowcept_dataclasses.task_message import (
    TaskMessage,
    Status,
)

from flowcept.commons import instrumentation_interceptor
from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import REPLACE_NON_JSON_SERIALIZABLE
from functools import wraps


def inspect_torch_tensor(tensor):
    tensor_inspection = {
        "id": id(tensor),
        "is_cuda": tensor.is_cuda,
        "is_cpu": tensor.is_cpu,
        "is_sparse": tensor.is_sparse,
        "shape": list(tensor.shape),
        "nbytes": tensor.nbytes,
        "numel": tensor.numel(),
        "density": torch.nonzero(tensor).size(0) / tensor.numel(),
    }
    return tensor_inspection


# TODO :ml-refactor: perhaps use a function to handle args which could be reused in used and generated.
def handle_args(*args, **kwargs):
    pass


# TODO :ml-refactor: perhaps I should specialize this to a torch_task...
def flowcept_task(func=None, **decorator_kwargs):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_message = TaskMessage()
            task_message.activity_id = func.__name__
            task_message.task_id = str(uuid.uuid4())

            # for key, value in decorator_kwargs.items():
            #     if key == 'workflow_id':
            #         task_message.workflow_id = value

            task_message.telemetry_at_start = (
                instrumentation_interceptor.telemetry_capture.capture()
            )
            task_message.started_at = time()
            task_message.used = {}
            if args is not None:
                # TODO :ml-refactor: we are assuming that the first argument is self. This assumption works well for our pytorch modules but this will not in general
                try:
                    if hasattr(args[0], "workflow_id"):
                        task_message.workflow_id = getattr(
                            args[0], "workflow_id"
                        )
                    task_message.activity_id = args[0].__class__.__name__
                    _custom_metadata = {}
                    for k in args[0].__dict__:
                        if not k.startswith("_") and k != "workflow_id":
                            _custom_metadata[k] = args[0].__dict__[k]
                    if len(_custom_metadata):
                        if REPLACE_NON_JSON_SERIALIZABLE:
                            task_message.custom_metadata = (
                                replace_non_serializable(_custom_metadata)
                            )
                        else:
                            task_message.custom_metadata = _custom_metadata

                except Exception as e:
                    flowcept.commons.logger.exception(e)
                    pass

                if len(args) > 1:
                    i = 1
                    for ag in args[1:]:
                        if type(ag) == torch.Tensor:
                            try:
                                task_message.used[
                                    f"tensor_{i}"
                                ] = inspect_torch_tensor(ag)
                            except Exception as e:
                                flowcept.commons.logger.exception(e)
                                pass
                        i += 1
            if kwargs is not None:
                task_message.used.update(kwargs)

                if (
                    "workflow_id" in kwargs
                    and kwargs["workflow_id"] is not None
                ):
                    task_message.workflow_id = kwargs.get("workflow_id", None)

            if REPLACE_NON_JSON_SERIALIZABLE:
                task_message.used = replace_non_serializable(
                    task_message.used
                )
            try:
                result = func(*args, **kwargs)
                task_message.status = Status.FINISHED
            except Exception as e:
                task_message.status = Status.ERROR
                result = None
                task_message.stderr = str(e)
            task_message.ended_at = time()
            task_message.telemetry_at_end = (
                instrumentation_interceptor.telemetry_capture.capture()
            )
            task_message.generated = (
                result  # TODO :ml-refactor: this will likely cause errors!
            )
            if REPLACE_NON_JSON_SERIALIZABLE:
                task_message.generated = replace_non_serializable(
                    task_message.generated
                )

            instrumentation_interceptor.intercept(task_message)

            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)
