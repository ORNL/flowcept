"""Event handler module."""

from watchdog.events import FileSystemEventHandler


class InterceptionEventHandler(FileSystemEventHandler):
    """Event handler class."""

    def __init__(self, interceptor_instance, callback_function):
        super().__init__()
        self.callback_function = callback_function
        self.interceptor_instance = interceptor_instance

    def on_modified(self, event):
        """Get on modified."""
        self.callback_function(self.interceptor_instance)
