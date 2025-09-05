"""Flowcept's module for Pytorch instrumentation."""

from time import time
from types import MethodType

import numpy as np

from flowcept.commons.utils import replace_non_serializable
from typing import Dict, Union, Sized, Iterator
import uuid

import torch
from torch import nn

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.configs import (
    INSTRUMENTATION,
    REPLACE_NON_JSON_SERIALIZABLE,
    INSTRUMENTATION_ENABLED,
    TELEMETRY_ENABLED,
)
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor
from flowcept.instrumentation.flowcept_task import get_current_context_task_id

TORCH_CONFIG = INSTRUMENTATION.get("torch")

REGISTER_WORKFLOW = TORCH_CONFIG.get("register_workflow", True)


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
        _interceptor: BaseInterceptor = None

        def __init__(self, *args, **kwargs):
            super(TorchModuleWrapper, self).__init__(*args, **kwargs)
            instrumentation_enabled = INSTRUMENTATION_ENABLED
            capture_enabled = kwargs.get("capture_enabled", True)
            if not instrumentation_enabled or not capture_enabled:
                return
            _what = TORCH_CONFIG.get("what")
            self._parent_enabled = _what is not None and "parent" in _what

            self._children_enabled = _what is not None and "children" in _what

            if self._parent_enabled:
                self.forward = self._our_forward_parent
            self._epochs_at_every = TORCH_CONFIG.get("capture_epochs_at_every", 1)
            self._children_mode = None
            self._should_update_children_forward = False
            self._children_tensor_inspection_enabled = False
            if self._children_enabled:
                self._children_mode = TORCH_CONFIG.get("children_mode", None)
                self._children_tensor_inspection_enabled = "inspection" in self._children_mode
                if self._children_mode is None:
                    raise Exception("You enabled children mode, but did not specify which mode.")

                self._child_forward_func = _get_our_child_forward_func(self._children_mode)
                for name, child in self.named_children():
                    child.__dict__["_parent_module"] = self
                    TorchModuleWrapper._original_children_forward_functions[child.__class__] = child.__class__.forward
                    child.forward = MethodType(self._child_forward_func, child)

            TorchModuleWrapper._interceptor = InstrumentationInterceptor.get_instance()
            self._current_epoch = -1

            self._module_name = cls.__name__
            self._current_forward_task_id = None
            self._should_get_profile = kwargs.get("get_profile", False)
            self._custom_metadata = kwargs.get("custom_metadata", None)
            self.parent_task_id = kwargs.get(
                "parent_task_id", get_current_context_task_id()
            )  # to be used by forward layers
            self.parent_workflow_id = kwargs.get("parent_workflow_id", Flowcept.current_workflow_id)
            self._campaign_id = kwargs.get("campaign_id", Flowcept.campaign_id)
            if kwargs.get("save_workflow", True):
                self.workflow_id = self._register_as_workflow()

        PARENT_FORWARD = "parent_forward"

        def _our_forward_parent(self, *args, **kwargs):
            if self._current_epoch % self._epochs_at_every != 0:
                return super(TorchModuleWrapper, self).forward(*args, **kwargs)

            started_at = time()
            self._current_forward_task_id = str(started_at)
            custom_metadata = {}
            if hasattr(self, "training"):
                custom_metadata["is_training"] = self.training
            used = {}
            if self._current_epoch < 1:
                used["tensor"] = _inspect_torch_tensor(args[0])

            forward_task = {
                "task_id": self._current_forward_task_id,
                "workflow_id": self.workflow_id,
                "activity_id": self._module_name,
                "started_at": started_at,
                "used": used,
                "parent_task_id": self.parent_task_id,
                "custom_metadata": custom_metadata,
                "subtype": TorchModuleWrapper.PARENT_FORWARD,
                # Following is ok. if an error happens, it will break before sending it
                "status": Status.FINISHED.value,
            }
            if kwargs is not None:
                forward_task["used"].update(kwargs)

            self._enable_children_forward()
            y = super(TorchModuleWrapper, self).forward(*args, **kwargs)
            self._disable_children_forward()

            if self._current_epoch < 1:
                forward_task["generated"] = {"tensor": _inspect_torch_tensor(y)}

            if TELEMETRY_ENABLED:
                tel = TorchModuleWrapper._interceptor.telemetry_capture.capture()
                forward_task["telemetry_at_end"] = tel.to_dict()

            TorchModuleWrapper._interceptor.intercept(forward_task)

            return y

        def _enable_children_forward(self):
            if "children" in TORCH_CONFIG.get("what", "parent_only") and "telemetry" in TORCH_CONFIG["children_mode"]:
                if self._epochs_at_every > 1 and self._should_update_children_forward:
                    self._update_children_with_our_forward()

        def _disable_children_forward(self):
            if "children" in TORCH_CONFIG.get("what", "parent_only") and "telemetry" in TORCH_CONFIG["children_mode"]:
                if self._epochs_at_every > 1 and self._should_update_children_forward:
                    self._update_children_with_original_forward()
                self._should_update_children_forward = True

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

        def _update_children_with_our_forward(self):
            for name, child in self.named_children():
                child.forward = MethodType(self._child_forward_func, child)

        def _update_children_with_original_forward(self):
            for name, child in self.named_children():
                original = TorchModuleWrapper._original_children_forward_functions[child.__class__]
                child.forward = MethodType(original, child)

        def _disable_children_tensor_inspection(self):
            self._children_tensor_inspection_enabled = False
            if self._children_mode in {"lightweight", "tensor_inspection"}:
                self._update_children_with_original_forward()
                # If we get to the original children forwards here, we should stick with them.
                self._should_update_children_forward = False
            elif self._children_mode == "telemetry_and_tensor_inspection":
                self._child_forward_func = _get_our_child_forward_func(mode="telemetry")
                if self._epochs_at_every == 1:
                    self._update_children_with_our_forward()
            else:
                return

        def new_batch(self, parent_task_id):
            self.parent_task_id = parent_task_id

        def new_epoch(self, parent_task_id):
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
            self.parent_task_id = parent_task_id
            if self._children_tensor_inspection_enabled and self._current_epoch >= 0:
                self._disable_children_tensor_inspection()
            self._current_epoch += 1

        def _register_as_workflow(self):
            """Register as a workflow."""
            workflow_obj = WorkflowObject()
            workflow_obj.workflow_id = str(uuid.uuid4())
            if not REGISTER_WORKFLOW:
                return workflow_obj.workflow_id
            workflow_obj.name = self._module_name
            workflow_obj.campaign_id = self._campaign_id
            workflow_obj.parent_workflow_id = self.parent_workflow_id
            _custom_metadata = self._custom_metadata or {}
            _custom_metadata["workflow_type"] = "TorchModule"
            workflow_obj.used = {"capture_at_every": self._epochs_at_every}

            if self._should_get_profile:
                profile = self._get_profile()
                _custom_metadata["model_profile"] = profile

            workflow_obj.custom_metadata = _custom_metadata
            TorchModuleWrapper._interceptor.send_workflow_message(workflow_obj)
            return workflow_obj.workflow_id

    def _inspect_inner_modules(model, modules_dict={}, in_named=None, first_level_child=True):
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
            if first_level_child:
                setattr(module, "first_level_child", True)
            _inspect_inner_modules(module, modules_dict, in_named=name, first_level_child=False)
        return modules_dict

    def _get_our_child_forward_func(mode):
        """Pick the torch_task function."""
        if "telemetry" in mode and not TELEMETRY_ENABLED:
            raise Exception(
                "Your telemetry settings are disabled but you chose a telemetry mode. Please revise your settings."
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
        tensor_inspection["is_sparse"] = tensor.is_sparse
        tensor_inspection["shape"] = list(tensor.shape)
        tensor_inspection["device"] = str(tensor.device)
        tensor_inspection["nbytes"] = tensor.nbytes
        tensor_inspection["numel"] = tensor.numel()
        tensor_inspection["density"] = torch.nonzero(tensor).size(0) / tensor.numel()
        return tensor_inspection

    def _get_forward_used_args(module, tensor):
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

    CHILD_FORWARD = "child_forward"

    def _our_forward_lightweight(self, *args, **kwargs):
        result = TorchModuleWrapper._original_children_forward_functions[self.__class__](self, *args, **kwargs)
        task_dict = dict(
            subtype=CHILD_FORWARD,
            workflow_id=self._parent_module.workflow_id,
            parent_task_id=self._parent_module._current_forward_task_id,
            activity_id=self.__class__.__name__,
            status=Status.FINISHED.value,
        )
        TorchModuleWrapper._interceptor.intercept(task_dict)
        return result

    def _our_forward_telemetry(self, *args, **kwargs):
        result = TorchModuleWrapper._original_children_forward_functions[self.__class__](self, *args, **kwargs)
        task_dict = dict(
            subtype=CHILD_FORWARD,
            workflow_id=self._parent_module.workflow_id,
            parent_task_id=self._parent_module._current_forward_task_id,
            activity_id=self.__class__.__name__,
            status=Status.FINISHED.value,
            telemetry_at_end=TorchModuleWrapper._interceptor.telemetry_capture.capture().to_dict(),
        )
        TorchModuleWrapper._interceptor.intercept(task_dict)
        return result

    def _our_forward_telemetry_tensor_inspection(self, *args, **kwargs):
        result = TorchModuleWrapper._original_children_forward_functions[self.__class__](self, *args, **kwargs)
        task_dict = dict(
            subtype=CHILD_FORWARD,
            workflow_id=self._parent_module.workflow_id,
            parent_task_id=self._parent_module._current_forward_task_id,
            activity_id=self.__class__.__name__,
            status=Status.FINISHED.value,
            telemetry_at_end=TorchModuleWrapper._interceptor.telemetry_capture.capture().to_dict(),
            used=_get_forward_used_args(self, args[0]),
            generated={"tensor": _inspect_torch_tensor(result)},
        )
        TorchModuleWrapper._interceptor.intercept(task_dict)
        return result

    def _our_forward_tensor_inspection(self, *args, **kwargs):
        result = TorchModuleWrapper._original_children_forward_functions[self.__class__](self, *args, **kwargs)
        task_dict = dict(
            subtype=CHILD_FORWARD,
            workflow_id=self._parent_module.workflow_id,
            parent_task_id=self._parent_module._current_forward_task_id,
            activity_id=self.__class__.__name__,
            status=Status.FINISHED.value,
            used=_get_forward_used_args(self, args[0]),
            generated={"tensor": _inspect_torch_tensor(result)},
        )
        TorchModuleWrapper._interceptor.intercept(task_dict)
        return result

    return TorchModuleWrapper


def _get_parent_loop_class(epoch_or_batch):
    loop_mode = TORCH_CONFIG.get(f"{epoch_or_batch}_loop", "default")
    if loop_mode == "lightweight":
        from flowcept.instrumentation.flowcept_loop import FlowceptLightweightLoop

        parent_class = FlowceptLightweightLoop
    else:
        from flowcept.instrumentation.flowcept_loop import FlowceptLoop

        parent_class = FlowceptLoop
    return parent_class


def _create_epoch_loop_class():
    parent_class = _get_parent_loop_class(epoch_or_batch="epoch")

    class FlowceptEpochLoop(parent_class):
        """Specialization of FlowceptLoop for Epoch Loops."""

        ACTIVITY_ID = "epochs_loop"

        def __init__(
            self,
            items: Union[Sized, Iterator, int],
            model: "flowcept_torch.TorchModuleWrapper",
            parent_task_id=None,
            workflow_id=None,
            capture_enabled=True,
        ):
            if not capture_enabled or TORCH_CONFIG.get("epoch_loop", None) is None or not INSTRUMENTATION_ENABLED:
                super().__init__(items=items, capture_enabled=False)
                return
            super().__init__(
                items,
                loop_name=FlowceptEpochLoop.ACTIVITY_ID,
                item_name="epoch",
                parent_task_id=parent_task_id,
                workflow_id=workflow_id,
            )
            self.model = model

        def _capture_iteration_bounds(self):
            super()._capture_iteration_bounds()
            self.model.new_epoch(self.get_current_iteration_id())

    return FlowceptEpochLoop


def _create_batch_loop_class():
    parent_class = _get_parent_loop_class(epoch_or_batch="batch")

    class FlowceptBatchLoop(parent_class):
        """
        Specialization of FlowceptLoop for Batch Loops.

        This class extends `FlowceptLoop` to handle batch-level iterations within
        a training or workflow loop. It optionally integrates with a `FlowceptEpochLoop`
        to capture hierarchical loop information.

        Parameters
        ----------
        items : Union[Sized, Iterator, int]
            The items to iterate over, which can be a collection, an iterator, or an integer
            specifying the number of iterations.
        epochs_loop : FlowceptEpochLoop, optional
            The epoch-level loop to associate with this batch loop. If `None`,
            loop capture is disabled.
        parent_task_id : str, optional
            The parent task ID to associate with the loop. If not provided, it will be
            inferred from `epochs_loop`.
        workflow_id : str, optional
            The workflow ID to associate with the loop. If not provided, it will be
            inferred from `epochs_loop`.
        step : str, default="train"
            A string representing the loop's activity step, e.g., "train" or "validate".
        items_length : int, optional
            The length of the items if it cannot be determined automatically.

        Notes
        -----
        To disable loop capture entirely, set `epochs_loop` to `None` during initialization.

        See Also
        --------
        FlowceptLoop : The base class for implementing loops.
        FlowceptEpochLoop : The parent loop for managing epoch-level iterations.
        """

        def __init__(
            self,
            items: Union[Sized, Iterator, int],
            epochs_loop=None,
            parent_task_id=None,
            workflow_id=None,
            step="train",
            items_length=0,
            capture_enabled=True,
        ):
            self._epochs_loop = epochs_loop
            if (
                (not capture_enabled)
                or (self._epochs_loop is None)
                or (not self._epochs_loop.enabled)
                or (TORCH_CONFIG.get("batch_loop", None) is None)
            ):
                super().__init__(items=items, items_length=items_length, capture_enabled=False)
                return
            self.activity_id = f"{step}_batch"
            super().__init__(
                items,
                loop_name=self.activity_id,
                item_name="batch",
                parent_task_id=parent_task_id or self._epochs_loop.get_current_iteration_id(),
                workflow_id=workflow_id or epochs_loop.workflow_id,
                items_length=items_length,
            )

        def _capture_iteration_bounds(self):
            super()._capture_iteration_bounds()
            if self._epochs_loop is not None:
                self._epochs_loop.model.new_batch(self.get_current_iteration_id())

    return FlowceptBatchLoop


FlowceptEpochLoop = _create_epoch_loop_class()
FlowceptBatchLoop = _create_batch_loop_class()
