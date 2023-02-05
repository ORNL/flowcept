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


class DaskSchedulerInterceptor(BaseInterceptor):
    def __init__(self, scheduler, plugin_key="dask"):
        self._scheduler = scheduler
        self._error_path = "scheduler_error.log"

        for f in [self._error_path]:
            if os.path.exists(f):
                os.remove(f)

        super().__init__(plugin_key)

    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass

    def callback(self, task_id, start, finish, *args, **kwargs):
        try:
            if task_id in self._scheduler.tasks:
                ts = self._scheduler.tasks[task_id]

            if ts.state == "waiting":
                task_msg = TaskMessage()
                task_msg.task_id = task_id
                task_msg.custom_metadata = {
                    "scheduler": self._scheduler.address_safe
                }
                task_msg.status = Status.SUBMITTED
                if self.settings.scheduler_create_timestamps:
                    task_msg.utc_timestamp = get_utc_now()

                if hasattr(ts, "group_key"):
                    task_msg.activity_id = ts.group_key

                if self.settings.scheduler_should_get_input:
                    if hasattr(ts, "run_spec"):
                        get_run_spec_data(task_msg, ts.run_spec)
                self.intercept(task_msg)

        except Exception as e:
            # TODO: use logger
            with open(self._error_path, "a+") as ferr:
                ferr.write(f"FullStateError={repr(e)}\n")


def get_times_from_task_state(task_msg, ts):
    for times in ts.startstops:
        if times["action"] == "compute":
            task_msg.start_time = times["start"]
            task_msg.end_time = times["stop"]


class DaskWorkerInterceptor(BaseInterceptor):
    def __init__(self, plugin_key="dask"):
        self._error_path = "worker_error.log"
        self._plugin_key = plugin_key

        # Worker-specific props
        self._worker = None

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

        # Note that both scheduler and worker get the exact same input.
        # Worker does not resolve intermediate inputs, just like the scheduler.

    def callback(self, task_id, start, finish, *args, **kwargs):
        try:
            if task_id not in self._worker.state.tasks:
                return

            ts = self._worker.state.tasks[task_id]

            task_msg = TaskMessage()
            task_msg.task_id = task_id

            if ts.state == "executing":
                task_msg.status = Status.RUNNING
                task_msg.address = self._worker.worker_address
                if self.settings.worker_create_timestamps:
                    task_msg.start_time = get_utc_now()
            elif ts.state == "memory":
                task_msg.status = Status.FINISHED
                if self.settings.worker_create_timestamps:
                    task_msg.end_time = get_utc_now()
                else:
                    get_times_from_task_state(task_msg, ts)
            elif ts.state == "error":
                task_msg.status = Status.ERROR
                if self.settings.worker_create_timestamps:
                    task_msg.end_time = get_utc_now()
                else:
                    get_times_from_task_state(task_msg, ts)
                task_msg.stderr = {
                    "exception": ts.exception_text,
                    "traceback": ts.traceback_text,
                }
            else:
                return

            if self.settings.worker_should_get_input:
                if hasattr(ts, "run_spec"):
                    get_run_spec_data(task_msg, ts.run_spec)

            if self.settings.worker_should_get_output:
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
