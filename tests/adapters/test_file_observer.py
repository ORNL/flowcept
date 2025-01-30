import os
import time
import unittest
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
import tempfile
import threading


class TestFileObserver(unittest.TestCase):
    def setUp(self):
        self.test_file = tempfile.NamedTemporaryFile(delete=False)
        self.test_file_name = self.test_file.name
        self.test_file.close()

        # Thread event to signal that the callback was called
        self.callback_called_event = threading.Event()

        # Define the callback function to be triggered on modification
        def callback(file_path):
            if file_path == self.test_file_name:
                print(f"Callback triggered for {file_path}")
                self.callback_called_event.set()

        # Create an event handler and bind it to the callback
        self.event_handler = FileSystemEventHandler()
        self.event_handler.on_modified = lambda event: callback(event.src_path)

        # Set up watchdog observer
        self.observer = PollingObserver()
        self.observer.schedule(self.event_handler, path=self.test_file_name, recursive=False)
        self.observer.start()

    def tearDown(self):
        # Stop the observer and remove the temporary file
        self.observer.stop()
        self.observer.join()
        os.unlink(self.test_file_name)

    def test_file_observer_callback(self):
        # Modify the file to trigger the callback
        with open(self.test_file_name, "a") as f:
            f.write("File has been modified.")
            f.flush()
            os.fsync(f.fileno())  # Ensure file system updates

        # Add a small delay to ensure the observer catches the event
        time.sleep(0.5)

        # Wait for the callback to be called (max wait 5 seconds)
        callback_triggered = self.callback_called_event.wait(timeout=5)

        # Assert that the callback was called
        self.assertTrue(callback_triggered, "Callback was not triggered upon file modification.")

        # Additional assertions to ensure file was actually modified
        with open(self.test_file_name, "r") as f:
            content = f.read()
            self.assertIn(
                "File has been modified.", content, "File modification did not occur as expected."
            )


if __name__ == "__main__":
    unittest.main()
