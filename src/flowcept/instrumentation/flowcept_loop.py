"""FlowCept Loop module."""

import uuid
from time import time
from typing import Union, Sized, Iterator, Dict

from flowcept import Flowcept
from flowcept.commons.vocabulary import Status
from flowcept.configs import INSTRUMENTATION_ENABLED, TELEMETRY_ENABLED
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


class FlowceptLoop:
    """
    A utility class to wrap and instrument iterable loops for telemetry and tracking.

    The `FlowceptLoop` class supports iterating over a collection of items or a numeric range
    while capturing metadata for each iteration and for the loop as a whole. This is particularly
    useful in scenarios where tracking and instrumentation of loop executions is required.

    Notes
    -----
    This class integrates with the `Flowcept` system for telemetry and tracking, ensuring
    detailed monitoring of loops and their iterations. It is designed for cases where
    capturing granular runtime behavior of loops is critical.
    """

    _interceptor = InstrumentationInterceptor.get_instance()

    def __init__(
        self,
        items: Union[Sized, Iterator, int],
        loop_name="loop",
        item_name="item",
        parent_task_id=None,
        workflow_id=None,
        items_length=0,
        capture_enabled=True,
    ):
        """
        Initialize a FlowceptLoop instance for tracking iterations.

        This constructor wraps an iterable, numeric range, or explicit iterator into a
        loop context where each iteration is instrumented with provenance and optional
        telemetry. If instrumentation is disabled, the loop behaves like a normal
        Python iterator with minimal overhead.

        Parameters
        ----------
        items : Union[Sized, Iterator, int]
            The items to iterate over. Can be:

            - A sized iterable (e.g., list, range).
            - An integer (interpreted as ``range(items)``).
            - An iterator (requires ``items_length`` if length cannot be inferred).
        loop_name : str, optional
            A descriptive name for the loop. Used in provenance as the loop's activity
            identifier. Default is ``"loop"``.
        item_name : str, optional
            The key name under which each iteration's item is recorded in provenance.
            Default is ``"item"``.
        parent_task_id : str, optional
            The identifier of a parent task, if this loop is nested within another task.
            Default is ``None``.
        workflow_id : str, optional
            Identifier for the workflow this loop belongs to. If not provided, it is
            inherited from the current Flowcept context or generated as a UUID.
        items_length : int, optional
            Explicit number of items if ``items`` is an iterator without a defined length.
            Default is ``0``.
        capture_enabled : bool, optional
            Whether to enable provenance/telemetry capture. If ``False``, the loop runs
            without instrumentation. Default is ``True``.

        Raises
        ------
        Exception
            If ``items`` is not a supported type (sized iterable, integer, or iterator).

        Notes
        -----
        - Each iteration is recorded with ``used`` (inputs) and optional ``generated``
          values, plus telemetry if enabled.
        - Iteration metadata is finalized at the end of each iteration and sent to the
          active Flowcept interceptor.
        """
        self._current_iteration_task = {}
        if not (INSTRUMENTATION_ENABLED and capture_enabled):
            # These do_nothing functions help reduce overhead if no instrumentation is needed
            # because we do this if not enabled only here and never again.
            self._next_func = self._do_nothing_next
            self.end_iter = self._do_nothing_in_end_iter
            self._iterator = iter(items)
            self.enabled = False
            return

        if hasattr(items, "__len__"):
            self._iterator = iter(items)
            self._max = len(items)
        elif isinstance(items, int):
            it = range(items)
            self._iterator = iter(it)
            self._max = len(it)
        elif isinstance(items, Iterator):
            if items_length > 0:
                self._iterator = items
                self._max = items_length
            else:
                # TODO: think of a better way to do it
                from flowcept.commons.flowcept_logger import FlowceptLogger

                FlowceptLogger().warning("If you know the length size of this iterator, lease inform it.")
                items = list(items)
                self._iterator = iter(items)
                self._max = len(items)
        else:
            raise Exception("Not supported iterator items type.")

        group_id = str(id(self) + id(self._iterator) + id(parent_task_id))
        self._group_id = group_id  # str(id(self))
        self.enabled = True
        self.end_iter = self._end_iter
        self._next_func = self._our_next
        self._next_counter = 0
        self._last_iteration_task = None
        self._loop_name = loop_name
        self._act_id = self._loop_name + "_iteration"
        self._item_name = item_name
        self._parent_task_id = parent_task_id
        self.workflow_id = workflow_id or Flowcept.current_workflow_id or str(uuid.uuid4())

    def __iter__(self):
        return self

    def __len__(self):
        return self._max

    def __next__(self):
        return self._next_func()

    def get_current_iteration_id(self):
        """Get current iteration's task id."""
        return self._current_iteration_task.get("task_id", None)

    def _do_nothing_next(self):
        return next(self._iterator)

    def _our_next(self):
        # Basic idea: the beginning of the current iteration is the end of the last
        if self._max <= 0:
            # Do nothing. Empty iteration
            return next(self._iterator)

        if self._next_counter == self._max:
            # End loop
            self._capture_iteration_bounds()

        self._current_item = next(self._iterator)

        if self._next_counter == 0:
            # Begin loop
            self._capture_iteration_bounds()
        elif self._next_counter <= self._max - 1:
            self._capture_iteration_bounds()

        self._next_counter += 1
        return self._current_item

    def _capture_iteration_bounds(self):
        if self._last_iteration_task is not None:
            self._end_iteration_task(self._last_iteration_task)

        self._current_iteration_task = self._begin_iteration_task()
        self._last_iteration_task = self._current_iteration_task

    def _begin_iteration_task(self):
        iteration_task = {
            "started_at": time(),
            "task_id": self._group_id + str(self._next_counter),
            "workflow_id": self.workflow_id,
            "activity_id": self._act_id,
            "group_id": self._group_id,
            "used": {"i": self._next_counter, self._item_name: self._current_item},
            "parent_task_id": self._parent_task_id,
        }
        return iteration_task

    def _end_iteration_task(self, _):
        self._last_iteration_task["status"] = Status.FINISHED.value
        if TELEMETRY_ENABLED:
            tel = FlowceptLoop._interceptor.telemetry_capture.capture()
            self._last_iteration_task["telemetry_at_end"] = tel.to_dict()
        FlowceptLoop._interceptor.intercept(self._last_iteration_task)

    def _do_nothing_in_end_iter(self, *args, **kwargs):
        pass

    def _end_iter(self, generated_value: Dict):
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
        self._current_iteration_task["generated"] = generated_value


class FlowceptLightweightLoop:
    """
    A utility class to wrap and instrument iterable loops for telemetry and tracking.

    The `FlowceptLightweightLoop` class supports iterating over a collection of items or a numeric
    range while capturing metadata for each iteration and for the loop as a whole.
    This is particularly useful in scenarios where tracking and instrumentation of loop executions is required.

    Parameters
    ----------
    items : Union[Sized, Iterator]
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

    _interceptor = InstrumentationInterceptor.get_instance()

    def __init__(
        self,
        items: Union[Sized, Iterator],
        loop_name="loop",
        item_name="item",
        parent_task_id=None,
        workflow_id=None,
        items_length=0,
        capture_enabled=True,
    ):
        """
        Initialize a FlowceptLightweightLoop instance for tracking iterations.

        This constructor provides a lower-overhead loop wrapper compared to
        ``FlowceptLoop``. Iterations are pre-registered as task objects, and capture
        primarily updates ``used`` and ``generated`` fields as the loop progresses.

        Parameters
        ----------
        items : Union[Sized, Iterator]
            The items to iterate over. Must either be:

            - A sized iterable (with ``__len__``).
            - An explicit iterator (length must be given by ``items_length``).
        loop_name : str, optional
            A descriptive name for the loop. Used in provenance as the loop's activity
            identifier. Default is ``"loop"``.
        item_name : str, optional
            The key name under which each iteration's item is recorded in provenance.
            Default is ``"item"``.
        parent_task_id : str, optional
            The identifier of a parent task, if this loop is nested within another task.
            Default is ``None``.
        workflow_id : str, optional
            Identifier for the workflow this loop belongs to. If not provided, it is
            inherited from the current Flowcept context or generated as a UUID.
        items_length : int, optional
            Explicit number of items if ``items`` is an iterator without a defined length.
            Default is ``0``.
        capture_enabled : bool, optional
            Whether to enable provenance/telemetry capture. If ``False``, the loop runs
            without instrumentation. Default is ``True``.

        Raises
        ------
        Exception
            If ``items`` is neither a sized iterable nor an iterator.

        Notes
        -----
        - This class is designed for high-performance scenarios with many iterations.
        - Iteration tasks are pre-allocated, and provenance capture is batched via
          the Flowcept interceptor.
        - Compared to ``FlowceptLoop``, this class avoids per-iteration telemetry
          overhead unless explicitly enabled.
        """
        if isinstance(items, Iterator):
            self._iterator = items
        else:
            self._iterator = iter(items)

        self._max = items_length or len(items)

        if not (INSTRUMENTATION_ENABLED and capture_enabled and self._max):
            # These do_nothing functions help reduce overhead if no instrumentation is needed
            # because we do this if not enabled only here and never again.
            self._next_func = self._do_nothing_next
            self.end_iter = self._do_nothing_in_end_iter
            self.enabled = False
            self.get_current_iteration_id = lambda: ""
            return

        self.enabled = True
        self._next_func = self._our_next
        self._next_counter = -1
        self._current_item = None
        self._loop_name = loop_name
        self._item_name = item_name
        self._group_id = str(id(self) + id(self._iterator) + id(parent_task_id))
        self._act_id = loop_name + "_iteration"
        self.workflow_id = workflow_id or Flowcept.current_workflow_id or str(uuid.uuid4())
        task_obj = {
            "workflow_id": self.workflow_id,
            "activity_id": self._act_id,
            "group_id": self._group_id,
            "generated": {},
            "status": Status.FINISHED.value,
        }
        if parent_task_id is not None:
            task_obj["parent_task_id"] = parent_task_id
        self._current_iteration_tasks = []
        for i in range(self._max):
            new_task = dict(task_obj)
            new_task["task_id"] = self._group_id + str(i)
            new_task["used"] = {"i": i, self._item_name: None}
            self._current_iteration_tasks.append(new_task)

    def __iter__(self):
        return self

    def __len__(self):
        return self._max

    def __next__(self):
        return self._next_func()

    def get_current_iteration_id(self):
        """Get current iteration's task id."""
        return self._group_id + str(self._next_counter)

    def _do_nothing_next(self):
        return next(self._iterator)

    def _do_nothing_in_end_iter(self, *args, **kwargs):
        pass

    def _our_next(self):
        # Basic idea: the beginning of the current iteration is the end of the last
        if self._next_counter == self._max - 1:
            # End loop
            self._capture_iteration_bounds()
            FlowceptLightweightLoop._interceptor.intercept_many(self._current_iteration_tasks)

        self._current_item = next(self._iterator)

        self._next_counter += 1

        self._capture_iteration_bounds()
        return self._current_item

    def _capture_iteration_bounds(self):
        self._current_iteration_tasks[self._next_counter]["used"][self._item_name] = self._current_item

    def end_iter(self, generated_value: Dict):
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
        self._current_iteration_tasks[self._next_counter]["generated"] = generated_value
