"""Pytorch module."""

from time import time
from types import MethodType

import numpy as np

from flowcept.commons.utils import replace_non_serializable
from typing import Dict
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
    REPLACE_NON_JSON_SERIALIZABLE,
)
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor
from flowcept.instrumentation.flowcept_task import get_current_context_task_id


def flowcept_torch(cls):
    """
    A wrapper function that instruments PyTorch modules for workflow monitoring.

    This decorator wraps a PyTorch module class to enable instrumentation of its `forward` method.
    The wrapper captures telemetry, tensor inspection, and profiling data during forward passes,
    allowing integration with monitoring tools like Flowcept.

    Parameters
    ----------
    cls : class
        A PyTorch module class (inherits from `torch.nn.Module`) to be wrapped.

    Returns
    -------
    class
        A wrapped version of the input PyTorch module class with instrumentation enabled.

    Optional Constructor Arguments
    ------------------------------
    get_profile : bool, optional
        If set to `True`, enables capturing the module's profile, such as the number of parameters,
        maximum tensor width, and inner modules. Default is `False`.
    custom_metadata : dict, optional
        A dictionary containing custom metadata to associate with the workflow. This metadata
        can include additional user-defined information to help with task identification and
        tracking.
    parent_task_id : str, optional
        The task ID of the parent task. It is used to establish a parent-child relationship
        between tasks during the forward execution of the module.
    parent_workflow_id : str, optional
        The workflow ID of the parent workflow. It is used to associate the current module's
        workflow with its parent workflow, allowing hierarchical workflow tracking.
    campaign_id : str, optional
        A user-defined campaign ID to group multiple workflows under a common identifier,
        useful for organizing and monitoring tasks that belong to the same experiment or campaign.
    save_workflow : bool, optional
        If set to `True` (default), the workflow is registered and sent to the interceptor.
        If set to `False`, the workflow registration step is skipped.

    Notes
    -----
    - If you use Optional Constructor Arguments, make sure you either specify them in your Module
      constructor signature or simply use **kwargs in the signature.
    - The wrapper can intercept both parent and child modules' forward calls based on configuration.
    - The instrumentation can operate in various modes such as lightweight, telemetry,
      tensor inspection, or combined telemetry and tensor inspection.
    - Workflow and task metadata, such as execution start/end times, tensor usage, and
      profiling details, are collected and sent for monitoring.
    - The behavior is controlled by a global configuration (`INSTRUMENTATION`) that
      specifies what to instrument and how.

    Examples
    --------
    >>> import torch
    >>> import torch.nn as nn
    >>> @flowcept_torch
    >>> class MyModel(nn.Module):
    ...     def __init__(self, get_profile=True, **kwargs):
    ...         super().__init__()
    ...         self.fc = nn.Linear(10, 1)
    ...
    ...     def forward(self, x):
    ...         return self.fc(x)
    ...
    >>> model = MyModel()
    >>> x = torch.randn(1, 10)
    >>> output = model(x)

    In the example above:
    - The `forward` method of `MyModel` and its children (if enabled) will be instrumented.
    - Workflow and task information, including `parent_task_id` and profiling details, will be
      recorded and sent to the configured interceptor.
    """

    class TorchModuleWrapper(cls):
        _original_children_forward_functions: Dict = {}
        interceptor: BaseInterceptor = None

        def __init__(self, *args, **kwargs):
            super(TorchModuleWrapper, self).__init__(*args, **kwargs)
            instrumentation_enabled = INSTRUMENTATION.get("enabled", False)
            if not instrumentation_enabled:
                return
            _what = INSTRUMENTATION.get("torch", {}).get("what")
            self._parent_enabled = _what is not None and "parent" in _what
            self._children_enabled = _what is not None and "children" in _what

            if self._parent_enabled:
                self.forward = self._our_parent_forward

            if self._children_enabled:
                mode = INSTRUMENTATION.get("torch", {}).get("children_mode", None)
                if mode is None:
                    raise Exception("You enabled children mode, but did not specify which mode.")

                child_forward_func = _get_child_our_forward_func(mode)
                for name, child in self.named_children():
                    if hasattr(child, "forward"):
                        child.__dict__["_parent_module"] = self
                        TorchModuleWrapper._original_children_forward_functions[child.__class__] = (
                            child.__class__.forward
                        )
                        child.forward = MethodType(child_forward_func, child)

            TorchModuleWrapper.interceptor = InstrumentationInterceptor.get_instance()

            self._module_name = cls.__name__
            self._current_forward_task_id = None

            self._should_get_profile = kwargs.get("get_profile", False)
            self._custom_metadata = kwargs.get("custom_metadata", None)
            self._parent_task_id = kwargs.get(
                "parent_task_id", get_current_context_task_id()
            )  # to be used by forward layers
            self._parent_workflow_id = kwargs.get(
                "parent_workflow_id", Flowcept.current_workflow_id
            )
            self._campaign_id = kwargs.get("campaign_id", Flowcept.campaign_id)
            if kwargs.get("save_workflow", True):
                self._workflow_id = self._register_as_workflow()

        def _get_profile(self):
            nparams = 0
            max_width = -1
            for p in self.parameters():
                m = np.max(p.shape)
                nparams += p.numel()
                if m > max_width:
                    max_width = m

            modules = _inspect_inner_modules(self)
            if REPLACE_NON_JSON_SERIALIZABLE:
                modules = replace_non_serializable(modules)

            # TODO: :ml-refactor: create a dataclass
            this_result = {
                "params": nparams,
                "max_width": int(max_width),
                "n_modules": len(modules),
                "modules": modules,
                "model_repr": repr(self),
            }

            return this_result

        def set_parent_task_id(self, parent_task_id):
            """
            Set the parent task ID for the current module.

            This method assigns the given task ID as the parent task ID for the current module.
            The parent task ID is used to establish a hierarchical relationship between tasks
            during workflow instrumentation.

            Parameters
            ----------
            parent_task_id : str
                The task ID of the parent task to associate with the current module.

            Notes
            -----
            The parent task ID is used to track dependencies and relationships between tasks
            when capturing telemetry or workflow execution data.
            """
            self._parent_task_id = parent_task_id

        def _our_parent_forward(self, *args, **kwargs):
            started_at = time()
            self._current_forward_task_id = str(started_at)
            forward_task = {
                "started_at": started_at,
                "task_id": self._current_forward_task_id,
                "workflow_id": self._workflow_id,
                "activity_id": self._module_name,
                "used": _inspect_torch_tensor(args[0]),
                "parent_task_id": self._parent_task_id,
                # "custom_metadata": {"subtype": "parent_forward"},
                "type": "task",
                # Following is ok. if an error happens, it will break before sending it
                "status": "FINISHED",
            }
            y = super().forward(*args, **kwargs)
            forward_task["generated"] = _inspect_torch_tensor(y)
            tel = TorchModuleWrapper.interceptor.telemetry_capture.capture()
            if tel:
                forward_task["telemetry_at_end"] = tel.to_dict()
            forward_task["ended_at"] = time()
            TorchModuleWrapper.interceptor.intercept(forward_task)
            return y

        def _register_as_workflow(self):
            """Register as a workflow."""
            workflow_obj = WorkflowObject()
            workflow_obj.workflow_id = str(uuid.uuid4())
            if not REGISTER_WORKFLOW:
                return workflow_obj.workflow_id
            workflow_obj.name = cls.__name__
            workflow_obj.campaign_id = self._campaign_id
            workflow_obj.parent_workflow_id = self._parent_workflow_id
            _custom_metadata = self._custom_metadata or {}
            _custom_metadata["workflow_type"] = "TorchModule"

            if self._should_get_profile:
                profile = self._get_profile()
                _custom_metadata["model_profile"] = profile

            workflow_obj.custom_metadata = _custom_metadata
            TorchModuleWrapper.interceptor.send_workflow_message(workflow_obj)
            return workflow_obj.workflow_id

    def _inspect_inner_modules(model, modules_dict={}, in_named=None):
        if not isinstance(model, nn.Module):
            return
        key = f"{model.__class__.__name__}_{id(model)}"
        modules_dict[key] = {
            "type": model.__class__.__name__,
        }
        if in_named is not None:
            modules_dict[key]["in_named"] = in_named
        modules_dict[key].update({k: v for k, v in model.__dict__.items() if not k.startswith("_")})
        for name, module in model.named_children():
            if isinstance(module, nn.Module):
                _inspect_inner_modules(module, modules_dict, in_named=name)
        return modules_dict

    def _get_child_our_forward_func(mode):
        """Pick the torch_task function."""
        if "telemetry" in mode and TELEMETRY_CAPTURE is None:
            raise Exception(
                "Your telemetry settings are null but you chose a "
                "telemetry mode. Please revise your settings."
            )
        elif mode == "lightweight":
            return _our_forward_lightweight
        elif mode == "tensor_inspection":
            return _our_forward_tensor_inspection
        elif mode == "telemetry":
            return _our_forward_telemetry
        elif mode == "telemetry_and_tensor_inspection":
            return _our_forward_telemetry_tensor_inspection
        else:
            raise NotImplementedError(f"There is no torch instrumentation mode {mode}")

    # TODO: move these functions to inside the wrapper class
    def _inspect_torch_tensor(tensor: torch.Tensor):
        _id = id(tensor)
        tensor_inspection = {"id": _id}
        # try:
        #     tensor_inspection["device"] = tensor.device.type
        # except Exception as e:
        #     logger.warning(f"For tensor {_id} could not get its device. Exc: {e}")
        tensor_inspection["is_sparse"] = tensor.is_sparse
        tensor_inspection["shape"] = list(tensor.shape)
        tensor_inspection["device"] = str(tensor.device)
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

    def _generated_used_tensor(module, tensor):
        used = {"tensor": _inspect_torch_tensor(tensor)}
        for k, v in vars(module).items():
            if not k.startswith("_"):
                if k == "forward" or callable(v):
                    continue
                elif isinstance(v, torch.Tensor):
                    used[k] = _inspect_torch_tensor(v)
                else:
                    used[k] = v
        return used

    def _run_forward(self, *args, **kwargs):
        started_at = time()
        result = TorchModuleWrapper._original_children_forward_functions[self.__class__](
            self, *args, **kwargs
        )
        task_dict = dict(
            type="task",
            started_at=started_at,
            task_id=str(started_at),
            workflow_id=self._parent_module._workflow_id,
            parent_task_id=self._parent_module._current_forward_task_id,
            activity_id=self.__class__.__name__,
            status="FINISHED",
        )
        return task_dict, result

    def _our_forward_lightweight(self, *args, **kwargs):
        task_dict, result = _run_forward(self, *args, **kwargs)
        TorchModuleWrapper.interceptor.intercept(task_dict)
        return result

    def _our_forward_telemetry(self, *args, **kwargs):
        task_dict, result = _run_forward(self, *args, **kwargs)
        tel = TorchModuleWrapper.interceptor.telemetry_capture.capture()
        if tel:
            task_dict["telemetry_at_end"] = tel.to_dict()
        TorchModuleWrapper.interceptor.intercept(task_dict)
        return result

    def _our_forward_telemetry_tensor_inspection(self, *args, **kwargs):
        task_dict, result = _run_forward(self, *args, **kwargs)
        task_dict["used"] = _generated_used_tensor(self, args[0])
        tel = TorchModuleWrapper.interceptor.telemetry_capture.capture()
        if tel:
            task_dict["telemetry_at_end"] = tel.to_dict()
        TorchModuleWrapper.interceptor.intercept(task_dict)
        return result

    def _our_forward_tensor_inspection(self, *args, **kwargs):
        task_dict, result = _run_forward(self, *args, **kwargs)
        task_dict["used"] = _generated_used_tensor(self, args[0])
        task_dict["generated"] = {"tensor": _inspect_torch_tensor(result)}
        TorchModuleWrapper.interceptor.intercept(task_dict)
        return result

    return TorchModuleWrapper
