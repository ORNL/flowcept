"""Event handler module."""
from pathlib import Path
from watchdog.events import FileSystemEventHandler


class InterceptionEventHandler(FileSystemEventHandler):
    """Event handler class."""

    def __init__(self, interceptor_instance, file_path_to_watch, callback_function):
        super().__init__()
        self.file_path_to_watch = file_path_to_watch
        self.callback_function = callback_function
        self.interceptor_instance = interceptor_instance

    def on_modified(self, event):
        """Get on modified."""
        if Path(event.src_path).resolve() == Path(self.file_path_to_watch).resolve():
            self.callback_function(self.interceptor_instance)
