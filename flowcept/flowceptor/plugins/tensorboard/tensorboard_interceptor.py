import sys
import os
import time

from watchdog.observers import Observer
from tbparse import SummaryReader

from flowcept.commons.flowcept_data_classes import TaskMessage, Status
from flowcept.commons.utils import get_utc_now
from flowcept.flowceptor.plugins.interceptor_state_manager import (
    InterceptorStateManager,
)
from flowcept.flowceptor.plugins.base_interceptor import (
    BaseInterceptor,
)
from flowcept.flowceptor.plugins.mlflow.interception_event_handler import (
    InterceptionEventHandler,
)


class TensorboardInterceptor(BaseInterceptor):
    def __init__(self, plugin_key="tensorboard"):
        super().__init__(plugin_key)
        self.state_manager = InterceptorStateManager(self.settings)
        self.log_metrics = set(self.settings.log_metrics)

    def callback(self):
        """
        This function is called whenever a change is identified in the data.
        It decides what to do in the event of a change.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        print("New tensorboard event file changed!")
        # TODO: now we're waiting for the file to be completely written.
        # Is there a better way to inform when the file writing is finished?
        time.sleep(self.settings.watch_interval_sec)

        reader = SummaryReader(self.settings.file_path)
        for child_event_file in reader.children:
            child_event = reader.children[child_event_file]
            if self.state_manager.has_element_id(child_event.log_path):
                print(f"Already extracted metric from {child_event_file}.")
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
                task_msg.used = tracked_tags.pop("hparams")
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
                    print("This is an error")  # TODO: logger

                self.intercept(task_msg)
                self.state_manager.add_element_id(child_event.log_path)

    def observe(self):
        event_handler = InterceptionEventHandler(
            self, self.__class__.callback
        )
        while not os.path.isdir(self.settings.file_path):
            print(
                f"I can't watch the file {self.settings.file_path},"
                f" as it does not exist."
            )
            print(
                f"\tI will sleep for {self.settings.watch_interval_sec} sec."
                f" to see if it appears."
            )
            time.sleep(self.settings.watch_interval_sec)

        observer = Observer()
        observer.schedule(
            event_handler, self.settings.file_path, recursive=True
        )
        observer.start()
        print(f"Watching {self.settings.file_path}")


if __name__ == "__main__":
    try:
        interceptor = TensorboardInterceptor()
        interceptor.observe()
        while True:
            time.sleep(interceptor.settings.watch_interval_sec)
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
