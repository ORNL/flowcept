import sys
import os
import time
from watchdog.observers import Observer
from flowcept.flowceptor.plugins.abstract_flowceptor import (
    AbstractFlowceptor,
)
from flowcept.flowceptor.plugins.interceptor_state_manager import (
    InterceptorStateManager,
)

from flowcept.flowceptor.plugins.mlflow.mlflow_dao import MLFlowDAO
from flowcept.flowceptor.plugins.mlflow.interception_event_handler import (
    InterceptionEventHandler,
)


class MLFlowInterceptor(AbstractFlowceptor):
    def __init__(self, plugin_key="mlflow"):
        super().__init__(plugin_key)
        self.state_manager = InterceptorStateManager(self.settings)
        self.dao = MLFlowDAO(self.settings)

    def intercept(self, message: dict):
        super().post_intercept(message)

    def callback(self):
        """
        This function is called whenever a change is identified in the data.
        It decides what to do in the event of a change.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        from time import sleep

        sleep(5)
        runs = self.dao.get_finished_run_uuids()
        for run_uuid_tuple in runs:
            run_uuid = run_uuid_tuple[0]
            if not self.state_manager.has_element_id(run_uuid):
                print(f"We need to intercept this Run: {run_uuid}")
                run_data = self.dao.get_run_data(run_uuid)
                self.state_manager.add_element_id(run_uuid)
                self.intercept(run_data.__dict__)

    def observe(self):
        event_handler = InterceptionEventHandler(
            self, MLFlowInterceptor.callback
        )
        while not os.path.isfile(self.settings.file_path):
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
        interceptor = MLFlowInterceptor()
        interceptor.observe()
        while True:
            time.sleep(interceptor.settings.watch_interval_sec)
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
