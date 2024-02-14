import os
import time

from watchdog.observers import Observer
from tbparse import SummaryReader
from watchdog.observers.polling import PollingObserver

from flowcept.commons.flowcept_dataclasses.task_message import (
    TaskMessage,
    Status,
)
from flowcept.commons.utils import get_utc_now
from flowcept.flowceptor.adapters.interceptor_state_manager import (
    InterceptorStateManager,
)
from flowcept.flowceptor.adapters.base_interceptor import (
    BaseInterceptor,
)
from flowcept.flowceptor.adapters.mlflow.interception_event_handler import (
    InterceptionEventHandler,
)


class TensorboardInterceptor(BaseInterceptor):
    def __init__(self, plugin_key="tensorboard"):
        super().__init__(plugin_key)
        self._observer: PollingObserver = None
        self.state_manager = InterceptorStateManager(self.settings)
        self.state_manager.reset()
        self.log_metrics = set(self.settings.log_metrics)

    def callback(self):
        """
        This function is called whenever a change is identified in the data.
        It decides what to do in the event of a change.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        self.logger.debug("New tensorboard directory event!")
        # TODO: now we're waiting for the file to be completely written.
        # Is there a better way to inform when the file writing is finished?
        time.sleep(self.settings.watch_interval_sec)

        reader = SummaryReader(self.settings.file_path)
        for child_event_file in reader.children:
            child_event = reader.children[child_event_file]
            if self.state_manager.has_element_id(child_event.log_path):
                self.logger.debug(
                    f"Already extracted metric from {child_event_file}."
                )
                continue
            event_tags = child_event.get_tags()

            tracked_tags = {}
            for tag in self.settings.log_tags:
                if len(event_tags[tag]):
                    df = child_event.__getattribute__(tag)
                    df_dict = dict(zip(df.tag, df.value))
                    tracked_tags[tag] = df_dict

            if tracked_tags.get("tensors") and len(
                self.log_metrics.intersection(tracked_tags["tensors"].keys())
            ):
                task_msg = TaskMessage()
                hparams = tracked_tags.get("hparams")
                if "workflow_id" in hparams:
                    task_msg.workflow_id = hparams.pop("workflow_id")
                if "activity_id" in hparams:
                    task_msg.activity_id = hparams.pop("activity_id")

                task_msg.used = hparams
                task_msg.generated = tracked_tags.pop("tensors")
                task_msg.utc_timestamp = get_utc_now()
                task_msg.status = Status.FINISHED
                task_msg.custom_metadata = {
                    "event_file": child_event_file,
                    "log_path": child_event.log_path,
                }

                if os.path.isdir(child_event.log_path):
                    event_files = os.listdir(child_event.log_path)
                    if len(event_files):
                        task_msg.task_id = event_files[0]

                if task_msg.task_id is None:
                    self.logger.error("This is an error")  # TODO: logger

                self.intercept(task_msg)
                self.state_manager.add_element_id(child_event.log_path)

    def start(self) -> "TensorboardInterceptor":
        super().start()
        self.observe()
        return self

    def stop(self) -> bool:
        self.logger.debug("Interceptor stopping...")
        super().stop()
        self._observer.stop()
        self.logger.debug("Interceptor stopped.")
        return True

    def observe(self):
        event_handler = InterceptionEventHandler(
            self, self.__class__.callback
        )
        while not os.path.isdir(self.settings.file_path):
            self.logger.debug(
                f"I can't watch the file {self.settings.file_path},"
                f" as it does not exist."
            )
            self.logger.debug(
                f"\tI will sleep for {self.settings.watch_interval_sec} sec."
                f" to see if it appears."
            )
            time.sleep(self.settings.watch_interval_sec)

        self._observer = Observer()
        self._observer.schedule(
            event_handler, self.settings.file_path, recursive=True
        )
        self._observer.start()
        self.logger.debug(f"Watching {self.settings.file_path}")
