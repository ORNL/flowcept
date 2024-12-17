"""FlowCept Loop module."""

import typing
import uuid
from time import time

from flowcept import Flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.vocabulary import Status
from flowcept.configs import INSTRUMENTATION_ENABLED
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


class FlowceptLoop:
    """
    A utility class to wrap and instrument iterable loops for telemetry and tracking.

    The `FlowceptLoop` class supports iterating over a collection of items or a numeric range
    while capturing metadata for each iteration and for the loop as a whole. This is particularly
    useful in scenarios where tracking and instrumentation of loop executions is required.

    Parameters
    ----------
    items : typing.Union[typing.Sized, int]
        The items to iterate over. Must either be an iterable with a `__len__` method or an integer
        representing the range of iteration.
    loop_name : str, optional
        A descriptive name for the loop (default is "loop").
    item_name : str, optional
        The name used for each item in the telemetry (default is "item").
    parent_task_id : str, optional
        The ID of the parent task associated with the loop, if applicable (default is None).
    workflow_id : str, optional
        The workflow ID to associate with this loop. If not provided, it will be generated or
        inferred from the current workflow context.

    Raises
    ------
    Exception
        If `items` is not an iterable with a `__len__` method or an integer.

    Notes
    -----
    This class integrates with the `Flowcept` system for telemetry and tracking, ensuring
    detailed monitoring of loops and their iterations. It is designed for cases where
    capturing granular runtime behavior of loops is critical.
    """

    def __init__(
        self,
        items: typing.Union[typing.Sized, int],
        loop_name="loop",
        item_name="item",
        parent_task_id=None,
        workflow_id=None,
    ):
        if hasattr(items, "__len__"):
            self._iterator = iter(items)
            self._max = len(items)
        elif isinstance(items, int):
            it = range(items)
            self._iterator = iter(it)
            self._max = len(it)
        else:
            raise Exception("You must use an iterable has at least a __len__ method defined.")

        self.current_iteration_task = {}
        self.whole_loop_task_id = str(id(self))

        if not INSTRUMENTATION_ENABLED:
            # These do_nothing functions help reduce overhead if no instrumenetation is needed
            # because we do this if not enabled only here and never again.
            self._next_func = self._do_nothing_next
            self.end_iter = self._do_nothing_in_end_iter
            return

        self.end_iter = self._end_iter
        self._next_func = self._our_next
        self._next_counter = 0
        self.logger = FlowceptLogger()
        self._interceptor = InstrumentationInterceptor.get_instance()
        self._last_iteration_task = None
        self._loop_name = loop_name
        self._item_name = item_name
        self._parent_task_id = parent_task_id
        self._workflow_id = workflow_id or Flowcept.current_workflow_id or str(uuid.uuid4())

    def __iter__(self):
        return self

    def __len__(self):
        return self._max

    def __next__(self):
        return self._next_func()

    def _begin_loop(self):
        self.logger.debug("Capturing loop init.")
        self.whole_loop_task = {
            "started_at": time(),
            "task_id": self.whole_loop_task_id,
            "type": "task",
            "activity_id": self._loop_name,
            "workflow_id": self._workflow_id,
            "custom_metadata": {"subtype": "whole_loop"},
        }
        if self._parent_task_id:
            self.whole_loop_task["parent_task_id"] = self._parent_task_id
        self._interceptor.intercept(self.whole_loop_task)
        self._capture_iteration_bounds()

    def _end_loop(self):
        self._capture_iteration_bounds()
        self.logger.debug("Capturing loop end.")
        # self._end_iteration_task(self._last_iteration_task)
        self.whole_loop_task["status"] = Status.FINISHED.value
        self.whole_loop_task["ended_at"] = time()
        self._interceptor.intercept(self.whole_loop_task)

    def _do_nothing_next(self):
        return next(self._iterator)

    def _our_next(self):
        # Basic idea: the beginning of the current iteration is the end of the last
        if self._max <= 0:
            # Do nothing. Empty iteration
            return next(self._iterator)

        if self._next_counter == self._max:
            self._end_loop()

        self._current_item = next(self._iterator)

        if self._next_counter == 0:
            self._begin_loop()
        # elif self._next_counter == self._max - 1:
        #     self._end_loop()
        elif self._next_counter <= self._max - 1:
            self._capture_iteration_bounds()

        self._next_counter += 1
        return self._current_item

    def _capture_iteration_bounds(self):
        if self._last_iteration_task is not None:
            self.logger.debug(f"Capturing the end of iteration {self._next_counter-1}.")
            self._end_iteration_task(self._last_iteration_task)

        self.logger.debug(f"Capturing the init of iteration {self._next_counter}.")
        self.current_iteration_task = self._begin_iteration_task()
        self._last_iteration_task = self.current_iteration_task

    def _begin_iteration_task(self):
        iteration_task = {
            "started_at": (started_at := time()),
            "task_id": str(started_at),
            "workflow_id": self._workflow_id,
            "activity_id": self._loop_name + "_iteration",
            "used": {"i": self._next_counter, self._item_name: self._current_item},
            "parent_task_id": self.whole_loop_task["task_id"],
            "type": "task",
        }
        tel = self._interceptor.telemetry_capture.capture()
        if tel:
            iteration_task["telemetry_at_start"] = tel.to_dict()
        return iteration_task

    def _end_iteration_task(self, iteration_task):
        iteration_task["status"] = "FINISHED"
        self._interceptor.intercept(self._last_iteration_task)

    def _do_nothing_in_end_iter(self, *args, **kwargs):
        pass

    def _end_iter(self, generated_value: typing.Dict):
        """
        Finalizes the current iteration by associating generated values with the iteration metadata.

        This method updates the metadata of the current iteration to include the values generated
        during the iteration, ensuring they are properly logged and tracked.

        Parameters
        ----------
        generated_value : dict
           A dictionary containing the generated values for the current iteration. These values
           will be stored in the `generated` field of the iteration's metadata.
        """
        self.current_iteration_task["generated"] = generated_value
