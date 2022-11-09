import time
from watchdog.observers import Observer
import sys
from datetime import datetime
from flowcept.flowceptor.plugins.abstract_flowceptor import AbstractFlowceptor


class MLFlowInterceptor(AbstractFlowceptor):

    def intercept(self, message: dict):
        pass

    def observe(self):
        observer = Observer()
        observer.schedule(self.callback, self.settings.file_path, recursive=True)
        observer.start()
        print(f"Watching {self.settings.file_path}")
        try:
            while True:
                time.sleep(self.settings.watch_interval_sec)

        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    def callback(self):
        print("File changed!")
        self.intercept()


if __name__ == "__main__":
    try:
        interceptor = MLFlowInterceptor("mlflow1")
        interceptor.observe()
    except KeyboardInterrupt:
        print('Interrupted')
        sys.exit(0)
