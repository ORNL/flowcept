from typing import Dict
import os
import pickle

from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)


class DaskSchedulerInterceptor(BaseInterceptor):
    def __init__(self, scheduler, plugin_key="dask"):
        self._scheduler = scheduler
        self._filepath = "scheduler.log"
        self._error_path = "scheduler_error.log"

        # Scheduler-specific props
        self._should_get_all_transitions = True
        self._should_get_input = True

        for f in [self._filepath, self._error_path]:
            if os.path.exists(f):
                os.remove(f)
        super().__init__(plugin_key)

    @staticmethod
    def get_run_spec_data_in_scheduler(run_spec):
        line = f""
        if run_spec.get("function"):
            line += (
                f", function_call={pickle.loads(run_spec.get('function'))}"
            )
        if run_spec.get("args"):
            line += f", function_args={pickle.loads(run_spec.get('args'))}"
        if run_spec.get("kwargs"):
            line += (
                f", function_kwargs={pickle.loads(run_spec.get('kwargs'))}"
            )
        return line

    def intercept(self, message: Dict):
        intercepted_message = {
            "task_id": message.get("task_id"),
            "custom_metadata": message.get("line"),
            "activity_id": "",
            "status": "",
            "used": {},
        }
        super().prepare_and_send(intercepted_message)

    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass

    def callback(self, task_id, start, finish, *args, **kwargs):
        msg = {"task_id": task_id}
        line = ""
        if self._should_get_all_transitions:
            line += (
                f"Key={task_id}, start={start}, finish={finish}, args={args}"
            )
            try:
                if kwargs:
                    if kwargs.get("type"):
                        kwargs["type"] = pickle.loads(kwargs.get("type"))
                    line += f", kwargs={kwargs}; "
            except Exception as e:
                with open(self._error_path, "a+") as ferr:
                    ferr.write(
                        f"should_get_all_transitions_error={repr(e)}\n"
                    )

        if self._should_get_input:
            try:
                ts = self._scheduler.tasks[task_id]
                if hasattr(ts, "group_key"):
                    line += f" FunctionName={ts.group_key};"
                if hasattr(ts, "run_spec"):
                    line += DaskSchedulerInterceptor.get_run_spec_data_in_scheduler(
                        ts.run_spec
                    )
            except Exception as e:
                with open(self._error_path, "a+") as ferr:
                    ferr.write(f"FullStateError={repr(e)}\n")

            line += "\n"

        msg["line"] = line
        self.intercept(msg)


class DaskWorkerInterceptor(BaseInterceptor):
    @staticmethod
    def get_run_spec_data_in_worker(run_spec):
        line = ""
        if hasattr(run_spec, "function"):
            line += f", function_call={pickle.loads(run_spec.function)}"
        if hasattr(run_spec, "args") and run_spec.args:
            line += f", function_args={pickle.loads(run_spec.args)}"
        if hasattr(run_spec, "kwargs") and run_spec.kwargs:
            line += f", function_kwargs={pickle.loads(run_spec.kwargs)}"
        return line

    def __init__(self, plugin_key="dask"):
        self._filepath = "worker.log"
        self._error_path = "worker_error.log"
        self._plugin_key = plugin_key

        # Worker-specific props
        self._worker = None
        self._worker_should_get_input = True
        self._worker_should_get_output = True

        for f in [self._filepath, self._error_path]:
            if os.path.exists(f):
                os.remove(f)

    def setup_worker(self, worker):
        """
        Dask Worker's constructor happens actually in this setup method.
        That's why we call the super() constructor here.
        """
        self._worker = worker
        super().__init__(self._plugin_key)

    def intercept(self, message: Dict):
        intercepted_message = {
            "task_id": message.get("task_id"),
            "custom_metadata": message.get("line"),
            "activity_id": "",
            "status": "",
            "used": {},
        }
        super().prepare_and_send(intercepted_message)

    def callback(self, task_id, start, finish, *args, **kwargs):
        msg = {}
        line = ""
        if self._worker_should_get_input and start == "released":
            line = f"Worker={self._worker.worker_address}; Key={task_id}; Start={start}; Finish={finish};"
            if task_id in self._worker.state.tasks:
                try:
                    ts = self._worker.state.tasks[task_id]
                    if hasattr(ts, "run_spec"):
                        line += (
                            DaskWorkerInterceptor.get_run_spec_data_in_worker(
                                ts.run_spec
                            )
                        )
                except Exception as e:
                    with open(self._error_path, "a+") as ferr:
                        ferr.write(f"\tFullStateError={repr(e)}\n")

        if self._worker_should_get_output and finish == "memory":
            try:
                if task_id in self._worker.data.memory:
                    line += f"Worker={self._worker.worker_address}; Key={task_id}; Output={self._worker.data.memory[task_id]}\n"
            except Exception as e:
                with open(self._error_path, "a+") as ferr:
                    ferr.write(f"should_get_output_error={repr(e)}\n")
        line += "\n"
        msg["line"] = line
        self.intercept(msg)

    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass
