"""Interceptor module."""

import inspect

from flowcept import WorkflowObject
from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
    Status,
)
from flowcept.flowceptor.adapters.base_interceptor import (
    BaseInterceptor,
)
from flowcept.commons.utils import get_utc_now, replace_non_serializable
from flowcept.configs import (
    TELEMETRY_CAPTURE,
    REPLACE_NON_JSON_SERIALIZABLE,
    REGISTER_WORKFLOW,
    ENRICH_MESSAGES,
)


def get_run_spec_data(task_msg: TaskObject, run_spec):
    """Get the run specs."""
    # def _get_arg(arg_name):
    #     if type(run_spec) == dict:
    #         return run_spec.get(arg_name, None)
    #     elif hasattr(run_spec, arg_name):
    #         return getattr(run_spec, arg_name)
    #     return None
    #
    # def _parse_dask_tuple(_tuple: tuple):
    #     forth_elem = None
    #     if len(_tuple) == 3:
    #         _, _, value_tuple = _tuple
    #     elif len(_tuple) == 4:
    #         _, _, value_tuple, forth_elem = _tuple
    #
    #     _, value = value_tuple
    #     if len(value) == 1:  # Value is always an array here
    #         value = value[0]
    #     ret_obj = {"value": value}
    #
    #     if forth_elem is not None and type(forth_elem) == dict:
    #         ret_obj.update(forth_elem)
    #     else:
    #         pass  # We don't know yet what to do if this happens. So just pass.
    #
    #     return ret_obj

    func = run_spec[0]
    args = run_spec[1]
    kwargs = run_spec[2]

    task_msg.used = {}
    if args:
        params = list(inspect.signature(func).parameters)
        for k, v in zip(params, args):
            task_msg.used[k] = v

    if kwargs:
        if "workflow_id" in kwargs and not task_msg.workflow_id:
            task_msg.workflow_id = kwargs.get("workflow_id")
            task_msg.used.update(kwargs)
            task_msg.used.pop("workflow_id", None)

    #
    # arg_val = _get_arg("args")
    # if arg_val is not None:
    #     picked_args = pickle.loads(arg_val)
    #     # pickled_args is always a tuple
    #     i = 0
    #     for arg in picked_args:
    #         task_msg.used[f"arg{i}"] = arg
    #         i += 1
    #
    # arg_val = _get_arg("kwargs")
    # if arg_val is not None:
    #     picked_kwargs = pickle.loads(arg_val)
    #     if "workflow_id" in picked_kwargs:
    #         task_msg.workflow_id = picked_kwargs.pop("workflow_id")
    #     if len(picked_kwargs):
    #         task_msg.used.update(picked_kwargs)

    # arg_val = _get_arg("task")  # This happens in case of client.map
    # if arg_val is not None and type(arg_val) == tuple:
    #     task_obj = _parse_dask_tuple(arg_val)
    #     if "workflow_id" in task_obj:
    #         task_msg.workflow_id = task_obj.pop("workflow_id")
    #     task_msg.used = task_obj["value"]

    if REPLACE_NON_JSON_SERIALIZABLE:
        task_msg.used = replace_non_serializable(task_msg.used)


def get_task_deps(task_state, task_msg: TaskObject):
    """Get the task dependencies."""
    if len(task_state.dependencies):
        task_msg.dependencies = [t.key for t in task_state.dependencies]
    if len(task_state.dependents):
        task_msg.dependents = [t.key for t in task_state.dependents]


def get_times_from_task_state(task_msg, ts):
    """Get the times."""
    for times in ts.startstops:
        if times["action"] == "compute":
            task_msg.started_at = times["start"]
            task_msg.ended_at = times["stop"]


class DaskSchedulerInterceptor(BaseInterceptor):
    """Dask scheduler."""

    def __init__(self, scheduler, plugin_key="dask"):
        self._scheduler = scheduler
        super().__init__(plugin_key)
        super().start(bundle_exec_id=self._scheduler.address)

    def callback(self, task_id, start, finish, *args, **kwargs):
        """Implement the callback."""
        try:
            if task_id in self._scheduler.tasks:
                ts = self._scheduler.tasks[task_id]

            if ts.state == "waiting":
                task_msg = TaskObject()
                task_msg.task_id = task_id

                task_msg.status = Status.SUBMITTED
                if self.settings.scheduler_create_timestamps:
                    task_msg.submitted_at = get_utc_now()

                get_task_deps(ts, task_msg)

                if hasattr(ts, "group_key"):
                    task_msg.activity_id = ts.group_key

                if self.settings.scheduler_should_get_input:
                    if hasattr(ts, "run_spec"):
                        get_run_spec_data(task_msg, ts.run_spec)

                if REGISTER_WORKFLOW:
                    if hasattr(self._scheduler, "current_workflow"):
                        wf_obj: WorkflowObject = self._scheduler.current_workflow
                        task_msg.workflow_id = wf_obj.workflow_id
                        self.send_workflow_message(wf_obj)
                    else:
                        # TODO: we can't do much if the user didn't register the wf
                        pass

                self.intercept(task_msg.to_dict())

        except Exception as e:
            self.logger.error("Error with dask scheduler!")
            self.logger.exception(e)


class DaskWorkerInterceptor(BaseInterceptor):
    """Dask worker."""

    def __init__(self, plugin_key="dask"):
        self._plugin_key = plugin_key
        self._worker = None
        # super().__init__ goes to setup_worker.

    def setup_worker(self, worker):
        """Set the worker.

        Dask Worker's constructor happens actually in this setup method.
        That's why we call the super() constructor here.
        """
        self._worker = worker
        super().__init__(self._plugin_key)
        # TODO: :refactor: This is just to avoid the auto-generation of
        # workflow id, which doesnt make sense in Dask case..
        self._generated_workflow_id = True
        super().start(bundle_exec_id=self._worker.scheduler.address)
        # Note that both scheduler and worker get the exact same input.
        # Worker does not resolve intermediate inputs, just like the scheduler.
        # But careful: we are only able to capture inputs in client.map on
        # workers.

    def callback(self, task_id, start, finish, *args, **kwargs):
        """Implement the callback."""
        try:
            if task_id not in self._worker.state.tasks:
                return

            ts = self._worker.state.tasks[task_id]

            task_msg = TaskObject()
            task_msg.task_id = task_id

            if ts.state == "executing":
                if TELEMETRY_CAPTURE is not None:
                    task_msg.telemetry_at_start = self.telemetry_capture.capture()
                task_msg.status = Status.RUNNING
                task_msg.address = self._worker.worker_address
                if self.settings.worker_create_timestamps:
                    task_msg.started_at = get_utc_now()
            elif ts.state == "memory":
                task_msg.status = Status.FINISHED
                if self.settings.worker_create_timestamps:
                    task_msg.ended_at = get_utc_now()
                else:
                    get_times_from_task_state(task_msg, ts)
                if TELEMETRY_CAPTURE is not None:
                    task_msg.telemetry_at_end = self.telemetry_capture.capture()

            elif ts.state == "error":
                task_msg.status = Status.ERROR
                if self.settings.worker_create_timestamps:
                    task_msg.ended_at = get_utc_now()
                else:
                    get_times_from_task_state(task_msg, ts)
                task_msg.stderr = {
                    "exception": ts.exception_text,
                    "traceback": ts.traceback_text,
                }
                if TELEMETRY_CAPTURE is not None:
                    task_msg.telemetry_at_end = self.telemetry_capture.capture()
            else:
                return

            if self.settings.worker_should_get_input:
                if hasattr(ts, "run_spec"):
                    get_run_spec_data(task_msg, ts.run_spec)

            if self.settings.worker_should_get_output:
                if task_id in self._worker.data.memory:
                    task_msg.generated = self._worker.data.memory[task_id]
                    if REPLACE_NON_JSON_SERIALIZABLE:
                        task_msg.generated = replace_non_serializable(task_msg.generated)
            if ENRICH_MESSAGES:
                task_msg.enrich(self._plugin_key)

            self.intercept(task_msg.to_dict())

        except Exception as e:
            self.logger.error(f"Error with dask worker: {self._worker.worker_address}")
            self.logger.exception(e)
