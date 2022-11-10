import time
from watchdog.observers import Observer
import sys
from datetime import datetime
from flowcept.flowceptor.plugins.abstract_flowceptor import AbstractFlowceptor

from flowcept.flowceptor.plugins.mlflow.interception_event_handler \
    import InterceptionEventHandler

class MLFlowInterceptor(AbstractFlowceptor):

    def intercept(self, message: dict):
        super().post_intercept(message)

    @staticmethod
    def callback(interceptor_instance: "MLFlowInterceptor"):
        """
        function that decides what do to when a change is identified.
        If it's an interesting change, it calls self.intercept; otherwise, let it go....
        """
        # TODO get latest info
        interceptor_instance.intercept({"nothing": "yet"})

    def observe(self):
        event_handler = InterceptionEventHandler(self, MLFlowInterceptor.callback)
        observer = Observer()
        observer.schedule(event_handler, self.settings.file_path, recursive=True)
        observer.start()
        print(f"Watching {self.settings.file_path}")
        try:
            while True:
                print("sleeping...")
                time.sleep(self.settings.watch_interval_sec)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()




if __name__ == "__main__":
    try:
        interceptor = MLFlowInterceptor("mlflow1")
        interceptor.observe()
    except KeyboardInterrupt:
        print('Interrupted')
        sys.exit(0)
