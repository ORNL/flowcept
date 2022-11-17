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
from flowcept.flowceptor.plugins.mlflow.mlflow_dataclasses import Run
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
        function that decides what do to when a change is identified.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """

        run_tuples = self.dao.get_runs()

        for run_tuple in run_tuples:
            run = Run(**run_tuple)
            print(run)
            # if run.run_uuid in :

        # TODO get latest info
        self.intercept({"nothing": "yet"})

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
        interceptor = MLFlowInterceptor("mlflow1")
        interceptor.observe()
        while True:
            time.sleep(interceptor.settings.watch_interval_sec)
    except KeyboardInterrupt:
        print("Interrupted")
        sys.exit(0)
