"""Interceptor module."""

import inspect

from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.flowceptor.adapters.base_interceptor import (
    BaseInterceptor,
)
from flowcept.commons.utils import get_utc_now, replace_non_serializable
from flowcept.configs import (
    TELEMETRY_CAPTURE,
    REPLACE_NON_JSON_SERIALIZABLE,
    ENRICH_MESSAGES,
    INSTRUMENTATION,
)
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


def get_run_spec_data(task_msg: TaskObject, run_spec):
    """Get the run specs."""
    func = run_spec[0]
    task_msg.activity_id = func.__name__
    args = run_spec[1]
    kwargs = run_spec[2]

    task_msg.used = {}
    if args:
        params = list(inspect.signature(func).parameters)
        for k, v in zip(params, args):
            task_msg.used[k] = v

    if kwargs:
        task_msg.used.update(kwargs)
        if "workflow_id" in kwargs and not task_msg.workflow_id:
            task_msg.workflow_id = kwargs.get("workflow_id")
            task_msg.used.pop("workflow_id", None)

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


class DaskWorkerInterceptor(BaseInterceptor):
    """Dask worker interceptor."""

    def __init__(self, plugin_key="dask", kind="dask"):
        self._plugin_key = plugin_key
        self._worker = None
        self.kind = kind
        # super().__init__ goes to setup_worker. I'm leaving this commented here as a reminder.

    def setup_worker(self, worker):
        """Set the worker.

        Dask Worker's constructor happens actually in this setup method.
        That's why we call the super() constructor here.
        """
        self._worker = worker
        super().__init__(plugin_key=self._plugin_key, kind=self.kind)
        self._worker.flowcept_tasks = {}
        # TODO: :refactor: Below is just to avoid the auto-generation of workflow id, which doesn't make sense in Dask.
        self._generated_workflow_id = True
        super().start(bundle_exec_id=self._worker.scheduler.address)

        self._worker._interceptor = self

        instrumentation = INSTRUMENTATION.get("enabled", False)
        if instrumentation:
            InstrumentationInterceptor.get_instance().start(
                bundle_exec_id=f"instrumentation_worker{self._worker.scheduler.address}"
            )

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

                self._worker.flowcept_tasks[task_id] = task_msg
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

            if hasattr(self._worker, "current_workflow_id"):
                task_msg.workflow_id = self._worker.current_workflow_id

            if hasattr(self._worker, "current_campaign_id"):
                task_msg.campaign_id = self._worker.current_campaign_id

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
