from typing import List, Dict

import torch
from torch import nn

import flowcept.commons
from flowcept.commons.utils import replace_non_serializable
from flowcept.configs import REPLACE_NON_JSON_SERIALIZABLE

from flowcept.instrumentation.decorators.flowcept_task import flowcept_task


def _inspect_torch_tensor(tensor):
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
                    for k in module_dict:
                        if not k.startswith("_") and k != "workflow_id":
                            custom_metadata[k] = module_dict[k]
                    if len(custom_metadata):
                        if REPLACE_NON_JSON_SERIALIZABLE:
                            custom_metadata = replace_non_serializable(
                                custom_metadata
                            )
                        task_message.custom_metadata = custom_metadata
                elif isinstance(arg, torch.Tensor):
                    args_handled[f"tensor_{i}"] = _inspect_torch_tensor(arg)
                else:
                    args_handled[f"arg_{i}"] = arg

        if kwargs is not None and len(kwargs):
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
    flowcept_torch_modules: Dict[nn.Module, nn.Module] = {}

    for module in modules:
        new_module = _create_dynamic_class(
            module, f"Flowcept{module.__name__}", {"workflow_id": workflow_id}
        )
        flowcept_torch_modules[module] = new_module

    return flowcept_torch_modules
