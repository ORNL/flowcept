from typing import Dict
import os
import pickle

from flowcept.commons.flowcept_data_classes import TaskMessage, Status
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)
from flowcept.commons.utils import get_utc_now


def get_run_spec_data(task_msg: TaskMessage, run_spec):
    def _get_arg(arg_name):
        if type(run_spec) == dict:
            return run_spec.get(arg_name, None)
        elif hasattr(run_spec, arg_name):
            return getattr(run_spec, arg_name)
        return None

    task_msg.used = {}
    arg_val = _get_arg("args")
    if arg_val is not None:
        picked_args = pickle.loads(arg_val)
        # pickled_args is always a tuple
        i = 0
        for arg in picked_args:
            task_msg.used[f"arg{i}"] = arg
            i += 1
    arg_val = _get_arg("kwargs")
    if arg_val is not None:
        picked_kwargs = pickle.loads(arg_val)
        if len(picked_kwargs):
            task_msg.used.update(picked_kwargs)

#
# def get_run_spec_data_in_worker(task_msg: TaskMessage, run_spec):
#     if hasattr(run_spec, "function"):
#         task_msg.activity_id = pickle.loads(run_spec.function)
#     if hasattr(run_spec, "args") and run_spec.args:
#         picked_args = pickle.loads(run_spec.get('args'))
#         if len(picked_args):
#             task_msg.used.update({"args": picked_args})
#     if hasattr(run_spec, "kwargs") and run_spec.kwargs:
#         picked_kwargs = pickle.loads(run_spec.get('kwargs'))
#         if len(picked_kwargs):
#             task_msg.used.update(picked_kwargs)


class DaskSchedulerInterceptor(BaseInterceptor):
    def __init__(self, scheduler, plugin_key="dask"):
        self._scheduler = scheduler
        self._error_path = "scheduler_error.log"

        # Scheduler-specific props
        self._should_get_input = True

        for f in [self._error_path]:
            if os.path.exists(f):
                os.remove(f)
        super().__init__(plugin_key)

    def intercept(self, message: TaskMessage):
        super().prepare_and_send(message)

    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass

    def callback(self, task_id, start, finish, *args, **kwargs):
        try:
            task_msg = TaskMessage()
            task_msg.task_id = task_id
            task_msg.custom_metadata = {"scheduler": self._scheduler.address_safe}
            task_msg.status = Status.SUBMITTED
            if task_id in self._scheduler.tasks:
                ts = self._scheduler.tasks[task_id]
                if hasattr(ts, "group_key"):
                    task_msg.activity_id = ts.group_key

                if self._should_get_input:
                    if hasattr(ts, "run_spec"):
                        get_run_spec_data(task_msg, ts.run_spec)
            self.intercept(task_msg)

        except Exception as e:
            # TODO: use logger
            with open(self._error_path, "a+") as ferr:
                ferr.write(f"FullStateError={repr(e)}\n")


class DaskWorkerInterceptor(BaseInterceptor):

    def __init__(self, plugin_key="dask"):
        self._error_path = "worker_error.log"
        self._plugin_key = plugin_key

        # Worker-specific props
        self._worker = None
        self._worker_should_get_input = True
        self._worker_should_get_output = True

        for f in [self._error_path]:
            if os.path.exists(f):
                os.remove(f)

    def setup_worker(self, worker):
        """
        Dask Worker's constructor happens actually in this setup method.
        That's why we call the super() constructor here.
        """
        self._worker = worker
        super().__init__(self._plugin_key)

    def intercept(self, message: TaskMessage):
        super().prepare_and_send(message)

    def callback(self, task_id, start, finish, *args, **kwargs):
        try:
            task_msg = TaskMessage()
            task_msg.task_id = task_id
            ts = None
            if task_id in self._worker.state.tasks:
                ts = self._worker.state.tasks[task_id]

            if start == "released":
                task_msg.status = Status.RUNNING
                task_msg.address = self._worker.worker_address
                task_msg.start_time = get_utc_now()
            elif finish == "memory":
                task_msg.end_time = get_utc_now()
                task_msg.status = Status.FINISHED
            elif finish == "error":
                task_msg.status = Status.ERROR
                if task_id in self._worker.state.tasks:
                    ts = self._worker.state.tasks[task_id]
                    task_msg.stderr = {
                        "exception": ts.exception_text,
                        "traceback": ts.traceback_text
                    }
            else:
                return

            if self._worker_should_get_input and ts:
                if hasattr(ts, "run_spec"):
                    get_run_spec_data(task_msg, ts.run_spec)

            if self._worker_should_get_output:
                if task_id in self._worker.data.memory:
                    task_msg.generated = self._worker.data.memory[task_id]

            self.intercept(task_msg)

        except Exception as e:
            with open(self._error_path, "a+") as ferr:
                ferr.write(f"should_get_output_error={repr(e)}\n")


    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass
