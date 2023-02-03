from typing import Dict
import os
import pickle

from flowcept.commons.flowcept_data_classes import TaskMessage, Status
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)


def get_run_spec_data(task_msg: TaskMessage, run_spec):
    def _get_arg(arg_name):
        if type(run_spec) == dict:
            return run_spec.get(arg_name, None)
        elif hasattr(run_spec, arg_name):
            return getattr(run_spec, arg_name)
        return None

    arg_val = _get_arg("function")
    # if arg_val is not None:
    #     task_msg.activity_id = pickle.loads(arg_val)
    arg_val = _get_arg("args")
    if arg_val is not None:
        picked_args = pickle.loads(arg_val)
        if len(picked_args) and task_msg.used is not None:
            task_msg.used.update({"args": picked_args})
    arg_val = _get_arg("kwargs")
    if arg_val is not None:
        picked_kwargs = pickle.loads(arg_val)
        if len(picked_kwargs) and task_msg.used is not None:
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
        self._should_get_all_transitions = True
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
        line = ""
        if self._should_get_input:
            task_msg = TaskMessage()
            task_msg.task_id = task_id
            task_msg.used = {}
            try:
                ts = self._scheduler.tasks[task_id]
                if hasattr(ts, "group_key"):
                    task_msg.activity_id = ts.group_key
                if hasattr(ts, "run_spec"):
                    get_run_spec_data(
                        task_msg,
                        ts.run_spec
                    )
            except Exception as e:
                # TODO: use logger
                with open(self._error_path, "a+") as ferr:
                    ferr.write(f"FullStateError={repr(e)}\n")

            task_msg.status = Status.SUBMITTED
            self.intercept(task_msg)


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
        task_msg = TaskMessage()
        task_msg.task_id = task_id
        #task_msg.used = {}
        if self._worker_should_get_input and start == "released":
            #task_msg.status = Status.SUBMITTED
            task_msg.private_ip = self._worker.worker_address
            # task_msg.start_time = start
            # task_msg.end_time = finish
            if task_id in self._worker.state.tasks:
                try:
                    ts = self._worker.state.tasks[task_id]
                    if hasattr(ts, "run_spec"):
                        get_run_spec_data(
                            task_msg,
                            ts.run_spec
                        )
                except Exception as e:
                    with open(self._error_path, "a+") as ferr:
                        ferr.write(f"\tFullStateError={repr(e)}\n")

        if self._worker_should_get_output and finish == "memory":
            try:
                if task_id in self._worker.data.memory:
                    task_msg.generated = self._worker.data.memory[task_id]
            except Exception as e:
                with open(self._error_path, "a+") as ferr:
                    ferr.write(f"should_get_output_error={repr(e)}\n")
            task_msg.status = Status.FINISHED
        task_msg.custom_metadata = {"worker": True}
        self.intercept(task_msg)

    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass
