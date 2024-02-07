import pickle

from flowcept.commons.flowcept_dataclasses.task_message import (
    TaskMessage,
    Status,
)
from flowcept.flowceptor.adapters.base_interceptor import (
    BaseInterceptor,
)
from flowcept.commons.utils import get_utc_now
from flowcept.configs import TELEMETRY_CAPTURE


class AIInterceptor(BaseInterceptor):
    def __init__(self, plugin_key):
        super().__init__(plugin_key)
        super().start()

    def callback(self, task_id, start, finish, *args, **kwargs):
        try:
            if task_id in self._scheduler.tasks:
                ts = self._scheduler.tasks[task_id]

            if ts.state == "waiting":
                task_msg = TaskMessage()
                task_msg.task_id = task_id
                task_msg.custom_metadata = {
                    "scheduler": self._scheduler.address_safe,
                    "scheduler_id": self._scheduler.id,
                    "scheduler_pid": self._scheduler.proc.pid,
                }
                task_msg.status = Status.SUBMITTED
                if self.settings.scheduler_create_timestamps:
                    task_msg.submitted_at = get_utc_now()

                get_task_deps(ts, task_msg)

                if hasattr(ts, "group_key"):
                    task_msg.activity_id = ts.group_key

                if self.settings.scheduler_should_get_input:
                    if hasattr(ts, "run_spec"):
                        get_run_spec_data(task_msg, ts.run_spec)
                self.intercept(task_msg)

        except Exception as e:
            self.logger.error("Error with dask scheduler!")
            self.logger.exception(e)

    def stop(self) -> bool:
        super().stop()
