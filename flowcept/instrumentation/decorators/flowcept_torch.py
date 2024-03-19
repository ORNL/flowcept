import uuid
from typing import List, Dict
import uuid

import torch
from torch import nn

import flowcept.commons
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons import logger
from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import REPLACE_NON_JSON_SERIALIZABLE, REGISTER_WORKFLOW

from flowcept.instrumentation.decorators.flowcept_task import flowcept_task


def _inspect_torch_tensor(tensor: torch.Tensor):
    _id = id(tensor)
    tensor_inspection = {"id": _id}
    # try:
    #     tensor_inspection["device"] = tensor.device.type
    # except Exception as e:
    #     logger.warning(f"For tensor {_id} could not get its device. Exc: {e}")
    try:
        tensor_inspection["is_sparse"] = tensor.is_sparse
    except Exception as e:
        logger.warning(
            f"For tensor {_id} could not get its is_sparse. Exc: {e}"
        )
    try:
        tensor_inspection["shape"] = tensor.shape
    except Exception as e:
        logger.warning(f"For tensor {_id} could not get its shape. Exc: {e}")
    # try:
    #     tensor_inspection["nbytes"] = tensor.nbytes
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


def torch_args_handler(task_message, *args, **kwargs):
    try:
        args_handled = {}
        if args is not None and len(args):
            for i in range(len(args)):
                arg = args[i]
                if isinstance(arg, nn.Module):
                    task_message.activity_id = arg.__class__.__name__
                    custom_metadata = {}
                    module_dict = arg.__dict__
                    if "workflow_id" in module_dict:
                        task_message.workflow_id = module_dict["workflow_id"]

                    # NO TORCH:
                    # for k in module_dict:
                    #     if k == "workflow_id":
                    #         task_message.workflow_id = module_dict[k]
                    #     elif not k.startswith("_"):
                    #         custom_metadata[k] = module_dict[k]
                    #
                    # if len(custom_metadata):
                    #     if REPLACE_NON_JSON_SERIALIZABLE:
                    #         custom_metadata = replace_non_serializable(
                    #             custom_metadata
                    #         )
                    #     task_message.custom_metadata = custom_metadata

                elif isinstance(arg, torch.Tensor):
                    # NO TORCH:
                    args_handled[f"tensor_{i}"] = _inspect_torch_tensor(arg)

                # NO TORCH
                # else:
                #     args_handled[f"arg_{i}"] = arg

                if task_message.workflow_id is None and hasattr(
                    arg, "workflow_id"
                ):
                    task_message.workflow_id = getattr(arg, "workflow_id")

        if kwargs is not None and len(kwargs):
            if task_message.workflow_id is None:
                task_message.workflow_id = kwargs.pop("workflow_id", None)
            args_handled.update(kwargs)
        if REPLACE_NON_JSON_SERIALIZABLE:
            args_handled = replace_non_serializable(args_handled)
        return args_handled
    except Exception as e:
        flowcept.commons.logger.exception(e)
        return None


@flowcept_task(args_handler=torch_args_handler)
def _our_forward(self, *args, **kwargs):
    return super(self.__class__, self).forward(*args, **kwargs)


def _create_dynamic_class(base_class, class_name, extra_attributes):
    attributes = {
        "__init__": lambda self, *args, **kwargs: super(
            self.__class__, self
        ).__init__(*args, **kwargs),
        "forward": lambda self, *args, **kwargs: _our_forward(
            self, *args, **kwargs
        ),
        **extra_attributes,
    }

    return type(class_name, (base_class,), attributes)


def register_modules(
    modules: List[nn.Module], workflow_id: str = None
) -> Dict[nn.Module, nn.Module]:
    flowcept_torch_modules: List[nn.Module] = []

    for module in modules:
        new_module = _create_dynamic_class(
            module, f"Flowcept{module.__name__}", {"workflow_id": workflow_id}
        )
        flowcept_torch_modules.append(new_module)
    if len(flowcept_torch_modules) == 1:
        return flowcept_torch_modules[0]
    else:
        return flowcept_torch_modules


def register_module_as_workflow(module: nn.Module, parent_workflow_id=None):
    workflow_obj = WorkflowObject()
    workflow_obj.workflow_id = str(uuid.uuid4())
    workflow_obj.parent_workflow_id = parent_workflow_id
    workflow_obj.name = module.__class__.__name__
    if REGISTER_WORKFLOW:
        flowcept.instrumentation.decorators.instrumentation_interceptor.send_workflow_message(
            workflow_obj
        )
    return workflow_obj.workflow_id
