import pika
import sys
import json
from typing import Dict
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)

import os
import pickle


class DaskInterceptor(BaseInterceptor):
    def __init__(self,  scheduler, plugin_key="dask"):
        self.scheduler = scheduler
        self.filepath = "scheduler.log"
        self.error_path = "scheduler_error.log"
        self._should_get_all_transitions = True
        self._should_get_input = True

        for f in [self.filepath, self.error_path]:
            if os.path.exists(f):
                os.remove(f)

        super().__init__(plugin_key)

    @staticmethod
    def get_run_spec_data(run_spec):
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
            "used": {}
        }
        super().prepare_and_send(intercepted_message)

    def observe(self):
        """
        Dask already observes task transitions,
        so we don't need to implement another observation.
        """
        pass

    def callback(self, who_sent: str, task_id, start, finish, *args, **kwargs):
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
                with open(self.error_path, "a+") as ferr:
                    ferr.write(
                        f"should_get_all_transitions_error={repr(e)}\n"
                    )

        if self._should_get_input:
            try:
                ts = self.scheduler.tasks[task_id]
                if hasattr(ts, "group_key"):
                    line += f" FunctionName={ts.group_key};"
                if hasattr(ts, "run_spec"):
                    line += DaskInterceptor.get_run_spec_data(
                        ts.run_spec
                    )
            except Exception as e:
                with open(self.error_path, "a+") as ferr:
                    ferr.write(f"FullStateError={repr(e)}\n")

            line += "\n"

        msg["line"] = line
        self.intercept(msg)

