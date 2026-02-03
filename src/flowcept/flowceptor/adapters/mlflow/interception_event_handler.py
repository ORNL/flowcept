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

    def _matches_watch_target(self, path):
        """Return True when a path matches the watch target.

        If the target is a directory, any event under that directory matches.
        If the target is a file, only the exact file path matches.
        """
        if not path:
            return False
        target = Path(self.file_path_to_watch).resolve()
        candidate = Path(path).resolve()
        if target.is_dir():
            try:
                candidate.relative_to(target)
                return True
            except ValueError:
                return False
        return candidate == target

    def _maybe_callback(self, event):
        """Invoke the callback when an event matches the watch target."""
        paths = [getattr(event, "src_path", None), getattr(event, "dest_path", None)]
        if any(self._matches_watch_target(path) for path in paths):
            self.callback_function(self.interceptor_instance)

    def on_modified(self, event):
        """Get on modified."""
        self._maybe_callback(event)

    def on_created(self, event):
        """Get on created."""
        self._maybe_callback(event)

    def on_moved(self, event):
        """Get on moved."""
        self._maybe_callback(event)
