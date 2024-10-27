"""Pytorch module."""

from time import time
from functools import wraps
import flowcept.commons
from flowcept.commons.flowcept_dataclasses.task_object import (
    Status,
)
from flowcept.instrumentation.decorators import instrumentation_interceptor
from typing import List, Dict
import uuid

import torch
from torch import nn

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.configs import (
    REGISTER_WORKFLOW,
    INSTRUMENTATION,
    TELEMETRY_CAPTURE,
)


# class FrequencyCount:
#     counter = 0
#     MAX = INSTRUMENTATION["torch"]["max_frequency"]


def _inspect_torch_tensor(tensor: torch.Tensor):
    _id = id(tensor)
    tensor_inspection = {"id": _id}
    # try:
    #     tensor_inspection["device"] = tensor.device.type
    # except Exception as e:
    #     logger.warning(f"For tensor {_id} could not get its device. Exc: {e}")
    tensor_inspection["is_sparse"] = tensor.is_sparse
    tensor_inspection["shape"] = list(tensor.shape)
    # tensor_inspection["nbytes"] = tensor.nbytes
    # except Exception as e:
    #     logger.warning(
    #         f"For tensor {_id}, could not get its nbytes. Exc: {e}"
    #     )
    # try: # no torch
    #     tensor_inspection["numel"] = tensor.numel()
    # except Exception as e:
    #     logger.warning(f"For tensor {_id}, could not get its numel. Exc: {e}")
    # try: # no torch
    #     tensor_inspection["density"] = (
    #         torch.nonzero(tensor).size(0) / tensor.numel()
    #     )
    # except Exception as e:
    #     logger.warning(
    #         f"For tensor {_id}, could not get its density. Exc: {e}"
    #     )
    return tensor_inspection


def full_torch_task(func=None):
    """Get pytorch task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            task_obj = {}
            task_obj["type"] = "task"
            task_obj["started_at"] = time()

            task_obj["activity_id"] = (func.__qualname__,)
            task_obj["task_id"] = str(id(task_obj))
            if hasattr(args[0], "parent_task_id"):
                task_obj["parent_task_id"] = args[0].parent_task_id
            task_obj["workflow_id"] = args[0].workflow_id
            task_obj["used"] = {
                "tensor": _inspect_torch_tensor(args[1]),
                **{k: v for k, v in vars(args[0]).items() if not k.startswith("_")},
            }
            task_obj["telemetry_at_start"] = (
                instrumentation_interceptor.telemetry_capture.capture().to_dict()
            )
            try:
                result = func(*args, **kwargs)
                task_obj["status"] = Status.FINISHED.value
            except Exception as e:
                task_obj["status"] = Status.ERROR.value
                result = None
                task_obj["stderr"] = str(e)
            task_obj["ended_at"] = time()
            task_obj["telemetry_at_end"] = (
                instrumentation_interceptor.telemetry_capture.capture().to_dict()
            )
            task_obj["generated"] = {
                "tensor": _inspect_torch_tensor(args[1]),
                # add other module metadata
            }
            instrumentation_interceptor.intercept(task_obj)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


#
# def _handle_torch_arg(task_dict_field, arg):
#     for k, v in vars(arg).items():
#         if not k.startswith("_"):
#             if isinstance(v, torch.Tensor):
#                 task_dict_field[k] = _inspect_torch_tensor(v)
#             elif callable(v):
#                 task_dict_field[k] = v.__qualname__
#             else:
#                 task_dict_field[k] = v


def lightweight_tensor_inspection_torch_task(func=None):
    """Get lightweight pytorch task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            used = {"tensor": _inspect_torch_tensor(args[1])}
            for k, v in vars(args[0]).items():
                if not k.startswith("_"):
                    if isinstance(v, torch.Tensor):
                        used[k] = _inspect_torch_tensor(v)
                    elif callable(v):
                        used[k] = v.__qualname__
                    else:
                        used[k] = v
            task_dict = dict(
                type="task",
                workflow_id=args[0].workflow_id,
                parent_task_id=args[0].parent_task_id,
                activity_id=func.__qualname__,
                used=used,
                generated={"tensor": _inspect_torch_tensor(result)},
            )
            instrumentation_interceptor.intercept(task_dict)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def lightweight_telemetry_tensor_inspection_torch_task(func=None):
    """Get lightweight tensor inspect task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            used = {"tensor": _inspect_torch_tensor(args[1])}
            for k, v in vars(args[0]).items():
                if not k.startswith("_"):
                    if isinstance(v, torch.Tensor):
                        used[k] = _inspect_torch_tensor(v)
                    elif callable(v):
                        used[k] = v.__qualname__
                    else:
                        used[k] = v
            task_dict = dict(
                type="task",
                workflow_id=args[0].workflow_id,
                parent_task_id=args[0].parent_task_id,
                activity_id=args[0].__class__.__name__,
                used=used,
                generated={"tensor": _inspect_torch_tensor(result)},
                telemetry_at_start=instrumentation_interceptor.telemetry_capture.capture().to_dict(),
            )
            instrumentation_interceptor.intercept(task_dict)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def lightweight_telemetry_torch_task(func=None):
    """Get lightweight telemetry torch task."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # We are commenting out everything we can to reduce overhead,
            # as this function is called multiple times in parallel
            result = func(*args, **kwargs)
            task_dict = dict(
                type="task",
                workflow_id=args[0].workflow_id,
                activity_id=func.__qualname__,
                telemetry_at_start=instrumentation_interceptor.telemetry_capture.capture().to_dict(),
            )
            instrumentation_interceptor.intercept(task_dict)
            return result

        return wrapper

    if func is None:
        return decorator
    else:
        return decorator(func)


def torch_task():
    """Get the torch task."""
    mode = INSTRUMENTATION["torch"]["mode"]
    if mode is None:
        return lambda _: _
    if "telemetry" in mode and TELEMETRY_CAPTURE is None:
        raise Exception(
            "Your telemetry settings are null but you chose a "
            "telemetry mode. Please revise your settings."
        )
    # elif mode == "lightweight_base":
    #     return lightweight_base_torch_task
    elif mode == "tensor_inspection":
        return lightweight_tensor_inspection_torch_task
    elif mode == "telemetry":
        return lightweight_telemetry_torch_task
    elif mode == "telemetry_and_tensor_inspection":
        return lightweight_telemetry_tensor_inspection_torch_task
    elif mode == "full":
        return full_torch_task
    else:
        raise NotImplementedError(f"There is no torch instrumentation mode {mode}")


@torch_task()
def _our_forward(self, *args, **kwargs):
    return super(self.__class__, self).forward(*args, **kwargs)


def _create_dynamic_class(base_class, class_name, extra_attributes):
    attributes = {
        "__init__": lambda self, *args, **kwargs: super(self.__class__, self).__init__(
            *args, **kwargs
        ),
        "forward": lambda self, *args, **kwargs: _our_forward(self, *args, **kwargs),
        **extra_attributes,
    }

    return type(class_name, (base_class,), attributes)


def register_modules(
    modules: List[nn.Module],
    workflow_id: str = None,
    parent_task_id: str = None,
) -> Dict[nn.Module, nn.Module]:
    """Register some modules."""
    flowcept_torch_modules: List[nn.Module] = []

    for module in modules:
        new_module = _create_dynamic_class(
            module,
            f"Flowcept{module.__name__}",
            extra_attributes={
                "workflow_id": workflow_id,
                "parent_task_id": parent_task_id,
            },
        )
        flowcept_torch_modules.append(new_module)
    if len(flowcept_torch_modules) == 1:
        return flowcept_torch_modules[0]
    else:
        return flowcept_torch_modules


def register_module_as_workflow(
    module: nn.Module,
    parent_workflow_id=None,
    # parent_task_id=None,
    custom_metadata: Dict = None,
):
    """Register as a workflow."""
    workflow_obj = WorkflowObject()
    workflow_obj.workflow_id = str(uuid.uuid4())
    workflow_obj.parent_workflow_id = parent_workflow_id
    workflow_obj.name = module.__class__.__name__
    _custom_metadata = custom_metadata or {}
    _custom_metadata["workflow_type"] = "TorchModule"
    workflow_obj.custom_metadata = custom_metadata
    # workflow_obj.parent_task_id = parent_task_id

    if REGISTER_WORKFLOW:
        flowcept.instrumentation.decorators.instrumentation_interceptor.send_workflow_message(
            workflow_obj
        )
    return workflow_obj.workflow_id
