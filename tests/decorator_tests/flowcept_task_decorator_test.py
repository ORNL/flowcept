import psutil
import uuid
from time import sleep
import pandas as pd
from time import time, sleep

from flowcept.commons import FlowceptLogger
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor

import flowcept.commons
import flowcept.instrumentation.decorators
from flowcept import FlowceptConsumerAPI

import unittest

from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.instrumentation.decorators.flowcept_task import (
    flowcept_task,
    lightweight_flowcept_task,
)


@flowcept_task
def decorated_static_function(df: pd.DataFrame, workflow_id=None):
    return {"decorated_static_function": 2}


@lightweight_flowcept_task
def decorated_all_serializable(x:int, workflow_id:str=None):
    sleep(1/10000)
    return {"yy": 33}


def not_decorated_func(x:int, workflow_id:str=None):
    sleep(1/10000)
    return {"yy": 33}


@lightweight_flowcept_task
def decorated_static_function2(workflow_id=None):
    return [2]


@lightweight_flowcept_task
def decorated_static_function3(x, workflow_id=None):
    return 3


def compute_statistics(array):
    import numpy as np

    stats = {
        "mean": np.mean(array),
        "median": np.median(array),
        "std_dev": np.std(array),
        "variance": np.var(array),
        "min_value": np.min(array),
        "max_value": np.max(array),
        "10th_percentile": np.percentile(array, 10),
        "25th_percentile": np.percentile(array, 25),
        "75th_percentile": np.percentile(array, 75),
        "90th_percentile": np.percentile(array, 90),
    }
    return stats


def calculate_overheads(decorated, not_decorated):
    keys = [
        "median",
        "25th_percentile",
        "75th_percentile",
        "10th_percentile",
        "90th_percentile",
    ]
    mean_diff = sum(
        abs(decorated[key] - not_decorated[key]) for key in keys
    ) / len(keys)
    overheads = [mean_diff / not_decorated[key] * 100 for key in keys]
    return overheads


def print_system_stats():
    # CPU utilization
    cpu_percent = psutil.cpu_percent(interval=1)

    # Memory utilization
    virtual_memory = psutil.virtual_memory()
    memory_total = virtual_memory.total
    memory_used = virtual_memory.used
    memory_percent = virtual_memory.percent

    # Disk utilization
    disk_usage = psutil.disk_usage('/')
    disk_total = disk_usage.total
    disk_used = disk_usage.used
    disk_percent = disk_usage.percent

    # Network utilization
    net_io = psutil.net_io_counters()
    bytes_sent = net_io.bytes_sent
    bytes_recv = net_io.bytes_recv

    print("System Utilization Summary:")
    print(f"CPU Usage: {cpu_percent}%")
    print(
        f"Memory Usage: {memory_percent}% (Used: {memory_used / (1024 ** 3):.2f} GB / Total: {memory_total / (1024 ** 3):.2f} GB)")
    print(
        f"Disk Usage: {disk_percent}% (Used: {disk_used / (1024 ** 3):.2f} GB / Total: {disk_total / (1024 ** 3):.2f} GB)")
    print(
        f"Network Usage: {bytes_sent / (1024 ** 2):.2f} MB sent / {bytes_recv / (1024 ** 2):.2f} MB received")


class DecoratorTests(unittest.TestCase):
    @lightweight_flowcept_task
    def decorated_function_with_self(self, x, workflow_id=None):
        sleep(x)
        return {"y": 2}

    def test_decorated_function(self):
        workflow_id = str(uuid.uuid4())
        # TODO :refactor-base-interceptor:
        with FlowceptConsumerAPI(
            interceptors=flowcept.instrumentation.decorators.instrumentation_interceptor
        ):
            self.decorated_function_with_self(x=0.1, workflow_id=workflow_id)
            decorated_static_function(df=pd.DataFrame(), workflow_id=workflow_id)
            decorated_static_function2(workflow_id=workflow_id)
            decorated_static_function3(x=0.1, workflow_id=workflow_id)
        print(workflow_id)

        assert assert_by_querying_tasks_until(
            filter={"workflow_id": workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == 4,
            max_time=60,
            max_trials=60,
        )


    def test_decorated_function_simple(
        self, max_tasks=10, start_doc_inserter=True, check_insertions=True
    ):
        workflow_id = str(uuid.uuid4())
        print(workflow_id)
        # TODO :refactor-base-interceptor:
        consumer = FlowceptConsumerAPI(
            interceptors=flowcept.instrumentation.decorators.instrumentation_interceptor,
            start_doc_inserter=start_doc_inserter,
        )
        consumer.start()
        t0 = time()
        for i in range(max_tasks):
            decorated_all_serializable(x=i, workflow_id=workflow_id)
        t1 = time()
        print("Decorated:")
        print_system_stats()
        consumer.stop()
        decorated = t1 - t0
        print(workflow_id)

        if check_insertions:
            assert assert_by_querying_tasks_until(
                filter={"workflow_id": workflow_id},
                condition_to_evaluate=lambda docs: len(docs) == max_tasks,
                max_time=60,
                max_trials=60,
            )

        t0 = time()
        for i in range(max_tasks):
            not_decorated_func(
                x=i, workflow_id=workflow_id
            )
        t1 = time()
        print("Not Decorated:")
        print_system_stats()
        not_decorated = t1 - t0
        return decorated, not_decorated


    def test_online_offline(self):
        flowcept.configs.DB_FLUSH_MODE = "offline"
        # flowcept.instrumentation.decorators.instrumentation_interceptor = (
        #     BaseInterceptor(plugin_key=None)
        # )
        print("Testing times with offline mode")
        self.test_decorated_function_timed()
        flowcept.configs.DB_FLUSH_MODE = "online"
        # flowcept.instrumentation.decorators.instrumentation_interceptor = (
        #     BaseInterceptor(plugin_key=None)
        # )
        print("Testing times with online mode")
        self.test_decorated_function_timed()

    def test_decorated_function_timed(self):
        print()
        times = []
        for i in range(10):
            times.append(
                self.test_decorated_function_simple(
                    max_tasks=10,#100000,
                    check_insertions=False,
                    start_doc_inserter=False,
                )
            )
        decorated = [decorated for decorated, not_decorated in times]
        not_decorated = [not_decorated for decorated, not_decorated in times]

        decorated_stats = compute_statistics(decorated)
        not_decorated_stats = compute_statistics(not_decorated)

        overheads = calculate_overheads(decorated_stats, not_decorated_stats)
        logger = FlowceptLogger()
        logger.critical(flowcept.configs.DB_FLUSH_MODE + ";" + str(overheads))

        n = "00002"
        print(f"#n={n}: Online double buffers; buffer size 100")
        print(f"decorated_{n} = {decorated_stats}")
        print(f"not_decorated_{n} = {not_decorated_stats}")
        print(f"diff_{n} = calculate_diff(decorated_{n}, not_decorated_{n})")
        print(f"'decorated_{n}': diff_{n},")
        print("Mode: " + flowcept.configs.DB_FLUSH_MODE)
        threshold = (
            10 if flowcept.configs.DB_FLUSH_MODE == "offline" else 210
        )  # %
        print("Threshold: ", threshold)
        print("Overheads: " + str(overheads))
        assert all(map(lambda v: v < threshold, overheads))
