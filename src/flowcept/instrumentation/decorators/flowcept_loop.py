import typing
import uuid
from collections.abc import Iterable
from time import time

from flowcept import Flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.vocabulary import Status
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


class FlowceptLoop:
    def __init__(self, items: typing.Union[typing.Iterable, int], loop_name="loop", item_name="item", parent_task_id=None, workflow_id=None):
        self._next_counter = 0
        self.logger = FlowceptLogger()
        self._interceptor = InstrumentationInterceptor.get_instance()
        if isinstance(items, range):
            self._iterable = items
            self._max = items.stop
        elif isinstance(items, int):
            self._iterable = range(items)
            self._max = self._iterable.stop
        elif isinstance(items, Iterable):
            self._iterable = items
            self._max = 10**100  # TODO: more complex iterables won't work; needs to implement the end of the loop
        else:
            raise NotImplementedError
        self._iterator = iter(self._iterable)
        self._current_iteration_task = {}
        self._loop_name = loop_name
        self._item_name = item_name
        self._parent_task_id = parent_task_id
        self._workflow_id = workflow_id or Flowcept.current_workflow_id or str(uuid.uuid4())

    def __iter__(self):
        return self

    def _capture_begin_loop(self):
        self.logger.debug(f"Registering loop init.")
        self.whole_loop_task = {
            "started_at": (started_at := time()),
            "task_id": str(started_at),
            "type": "task",
            "activity_id": self._loop_name,
            "workflow_id": self._workflow_id
        }
        if self._parent_task_id:
            self.whole_loop_task["parent_task_id"] = self._parent_task_id

    def _capture_end_loop(self):
        self.logger.debug("Registering the end of the loop.")
        self.whole_loop_task["status"] = Status.FINISHED.value
        self.whole_loop_task["ended_at"] = self._current_iteration_task["ended_at"]
        self._interceptor.intercept(self.whole_loop_task)

    def __next__(self):
        self.logger.debug(f"Calling next for the {self._next_counter}th time.")
        self._next_counter += 1
        if self._next_counter == 1:
            self._capture_begin_loop()
        elif self._next_counter > self._max:
            self._capture_end_loop()

        item = next(self._iterator)
        if self._next_counter <= self._max:
            self.logger.debug(f"Registering the init of the {self._next_counter - 1}th iteration.")
            self._current_iteration_task = {
                "workflow_id": self._workflow_id,
                "activity_id": self._loop_name + "_iteration",
                "used": {
                    "i": self._next_counter-1,
                    self._item_name: item
                },
                "parent_task_id": self.whole_loop_task["task_id"],
                "started_at": time(),
                "type": "task"
            }
        return item

    def end_iter(self, value: typing.Dict):
        self.logger.debug(f"Registering the end of the {self._next_counter - 1}th iteration.")
        self._current_iteration_task["generated"] = value
        self._current_iteration_task["ended_at"] = time()
        self._current_iteration_task["status"] = Status.FINISHED.value
        self._interceptor.intercept(self._current_iteration_task)

