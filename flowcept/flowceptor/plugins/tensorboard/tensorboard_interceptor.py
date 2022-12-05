import sys
import os
import time

from watchdog.observers import Observer
from tbparse import SummaryReader

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

    def intercept(self, message: dict):
        print(f"Going to intercept: {message}")
        super().post_intercept(message)

    def callback(self):
        """
        This function is called whenever a change is identified in the data.
        It decides what to do in the event of a change.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        print("New tensorboard event file changed!")
        # TODO: we're waiting for the file to be completely written.
        # Is there a better way to be informed when the file is finished?
        time.sleep(self.settings.watch_interval_sec)

        reader = SummaryReader(self.settings.file_path)
        for child_event_file in reader.children:
            child_event = reader.children[child_event_file]
            if self.state_manager.has_element_id(child_event.log_path):
                print(f"Already extracted metric from {child_event_file}.")
                continue
            event_tags = child_event.get_tags()
            msg = dict()
            found_metric = False
            for tag in self.settings.log_tags:
                if len(event_tags[tag]):
                    msg["event_file"] = child_event_file
                    msg["log_path"] = child_event.log_path
                    df = child_event.__getattribute__(tag)
                    df_dict = dict(zip(df.tag, df.value))
                    msg[tag] = df_dict
                    if not found_metric:
                        for tracked_metric in self.settings.log_metrics:
                            if tracked_metric in df_dict:
                                found_metric = True
                                print("Found metric in this file!")
                                break
            if found_metric:
                # Only intercept if we find a tracked metric in the event
                self.intercept(msg)
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
