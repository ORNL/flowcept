from queue import Queue
from typing import Union, List, Dict, Callable

import msgpack
from redis import Redis
from redis.client import PubSub
from threading import Thread, Lock, Event
from time import time, sleep

import flowcept.commons
from flowcept.commons.daos.keyvalue_dao import KeyValueDAO
from flowcept.commons.utils import perf_log
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_CHANNEL,
    REDIS_PASSWORD,
    JSON_SERIALIZER,
    REDIS_BUFFER_SIZE,
    REDIS_INSERTION_BUFFER_TIME,
    PERF_LOG,
    REDIS_URI,
)

from flowcept.commons.utils import GenericJSONEncoder


class AutoflushBuffer:
    def __init__(
        self,
        max_size,
        flush_interval,
        flush_function: Callable,
        *flush_function_args,
        **flush_function_kwargs,
    ):
        self.logger = FlowceptLogger()
        self._max_size = max_size
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

    def add(self, item):
        # if self.stop_event.is_set():
        #     return
        buffer = self._buffers[self._current_buffer_index]
        buffer.append(item)
        if len(buffer) >= self._max_size:
            self._swap_event.set()

    def time_based_flush(self):
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
        self._stop_event.set()
        self._swap_event.set()
        self._flush_thread.join()
        self._timer_thread.join()
        self._do_flush()
