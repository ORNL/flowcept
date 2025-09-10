"""Autoflush module."""

from typing import Callable
from threading import Thread, Event


class AutoflushBuffer:
    """Autoflush class."""

    def __init__(
        self,
        flush_function: Callable,
        max_size=None,
        flush_interval=None,
        flush_function_args=[],
        flush_function_kwargs={},
    ):
        self._max_size = max_size or float("inf")
        self._flush_interval = flush_interval or float("inf")
        self._flush_interval = flush_interval
        self._buffers = [[], []]
        self._current_buffer_index = 0
        self._swap_event = Event()
        self._stop_event = Event()

        self._timer_thread = Thread(target=self.time_based_flush)
        self._timer_thread.start()

        self._flush_thread = Thread(target=self._flush_buffers)
        self._flush_thread.start()

        self._flush_function = flush_function
        self._flush_function_args = flush_function_args
        self._flush_function_kwargs = flush_function_kwargs

    def append(self, item):
        """Append it."""
        buffer = self._buffers[self._current_buffer_index]
        buffer.append(item)
        if len(buffer) >= self._max_size:
            self._swap_event.set()

    def extend(self, items):
        """Extend it."""
        buffer = self._buffers[self._current_buffer_index]
        buffer.extend(items)
        if len(buffer) >= self._max_size:
            self._swap_event.set()

    @property
    def current_buffer(self):
        """Return the currently active buffer (read-only)."""
        return self._buffers[self._current_buffer_index]

    def time_based_flush(self):
        """Time flush."""
        while not self._stop_event.is_set():
            self._swap_event.wait(self._flush_interval)
            if not self._stop_event.is_set():
                self._swap_event.set()

    def _do_flush(self):
        old_buffer_index = self._current_buffer_index
        self._current_buffer_index = 1 - self._current_buffer_index
        old_buffer = self._buffers[old_buffer_index]
        if old_buffer:
            self._flush_function(
                old_buffer[:],
                *self._flush_function_args,
                **self._flush_function_kwargs,
            )
            self._buffers[old_buffer_index] = []

    def _flush_buffers(self):
        while not self._stop_event.is_set() or any(self._buffers):
            self._swap_event.wait()
            self._swap_event.clear()

            self._do_flush()

            if self._stop_event.is_set():
                break

    def stop(self):
        """Stop it."""
        self._stop_event.set()
        self._swap_event.set()
        self._flush_thread.join()
        self._timer_thread.join()
        self._do_flush()
