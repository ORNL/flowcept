import numpy as np
import psutil
import uuid
import random
from unittest.mock import patch
import pandas as pd
from time import time, sleep

import unittest

import flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.commons.vocabulary import Status
from flowcept import Flowcept, lightweight_flowcept_task, flowcept_task


def calc_time_to_sleep() -> float:
    l = list()
    matrix_size = 100
    t0 = time()
    matrix_a = np.random.rand(matrix_size, matrix_size)
    matrix_b = np.random.rand(matrix_size, matrix_size)
    result_matrix = np.dot(matrix_a, matrix_b)
    d = dict(
        a=time(),
        b=str(uuid.uuid4()),
        c="aaa",
        d=123.4,
        e={"r": random.randint(1, 100)},
        shape=list(result_matrix.shape),
    )
    l.append(d)
    t1 = time()
    sleep_time = (t1 - t0) * 1.1
    print("Sleep time", sleep_time)
    return sleep_time


TIME_TO_SLEEP = calc_time_to_sleep()


@flowcept_task
def decorated_static_function(df: pd.DataFrame):
    return pd.DataFrame([3])


@flowcept_task
def decorated_static_function2(x):
    return {"y": 2}


@flowcept_task(output_names="z")
def decorated_static_function3(x, y):
    return 5


@flowcept_task(output_names=("z", "w"))
def decorated_static_function4(x, y):
    return 6, 7





@lightweight_flowcept_task
def decorated_all_serializable(x: int):
    sleep(TIME_TO_SLEEP)
    return {"yy": 33}


def not_decorated_func(x: int):
    sleep(TIME_TO_SLEEP)
    return {"yy": 33}


@lightweight_flowcept_task
def lightweight_decorated_static_function2():
    return [2]


@lightweight_flowcept_task
def lightweight_decorated_static_function3(x):
    return 3


def parse_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=int, required=True, help="An integer argument")
    parser.add_argument("--b", type=str, required=True, help="A string argument")
    return parser.parse_known_args()


@flowcept_task
def process_arguments_task(known_args, unknown_args):
    print(known_args, unknown_args)


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
    mean_diff = sum(abs(decorated[key] - not_decorated[key]) for key in keys) / len(keys)
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
    disk_usage = psutil.disk_usage("/")
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
        f"Memory Usage: {memory_percent}% (Used: {memory_used / (1024 ** 3):.2f} GB / Total: {memory_total / (1024 ** 3):.2f} GB)"
    )
    print(
        f"Disk Usage: {disk_percent}% (Used: {disk_used / (1024 ** 3):.2f} GB / Total: {disk_total / (1024 ** 3):.2f} GB)"
    )
    print(
        f"Network Usage: {bytes_sent / (1024 ** 2):.2f} MB sent / {bytes_recv / (1024 ** 2):.2f} MB received"
    )


def simple_decorated_function(max_tasks=10, enable_persistence=True, check_insertions=True):
    # TODO :refactor-base-interceptor:
    consumer = Flowcept(start_persistence=enable_persistence)
    consumer.start()
    t0 = time()
    for i in range(max_tasks):
        decorated_all_serializable(x=i)
    t1 = time()
    print("Decorated:")
    print_system_stats()
    consumer.stop()
    decorated = t1 - t0

    if check_insertions:
        assert assert_by_querying_tasks_until(
            filter={"workflow_id": Flowcept.current_workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == max_tasks,
            max_time=60,
            max_trials=60,
        )

    t0 = time()
    for i in range(max_tasks):
        not_decorated_func(x=i)
    t1 = time()
    print("Not Decorated:")
    print_system_stats()
    not_decorated = t1 - t0
    return decorated, not_decorated


class DecoratorTests(unittest.TestCase):
    @lightweight_flowcept_task
    def lightweight_decorated_function_with_self(self, x):
        sleep(TIME_TO_SLEEP)
        return {"y": 2}

    def test_lightweight_decorated_function(self):
        with Flowcept():
            self.lightweight_decorated_function_with_self(x=0.1)
            lightweight_decorated_static_function2()
            lightweight_decorated_static_function3(x=0.1)

        sleep(1)
        assert assert_by_querying_tasks_until(
            filter={"workflow_id": Flowcept.current_workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == 3,
            max_time=60,
            max_trials=30,
        )
        tasks = Flowcept.db.query({"workflow_id": Flowcept.current_workflow_id})
        for t in tasks:
            assert t["task_id"]

    def test_decorated_function(self):
        # Compare this with the test_lightweight_decorated_function;
        # Here, Flowcept manages the workflow_id for the user;
        # Using the light decorator, the user has to control it.
        with Flowcept():
            print(Flowcept.current_workflow_id)
            decorated_static_function(df=pd.DataFrame([1]))
            decorated_static_function2(x=1)
            decorated_static_function2(2)
            try:
                decorated_static_function3(3, x=4)
            except Exception as e:
                print("Expected exception because the arg x should be y, like the func call below.", e)

            decorated_static_function3(3, y=4)
            decorated_static_function4(3, y=4)

        sleep(1)
        assert assert_by_querying_tasks_until(
            filter={"workflow_id": Flowcept.current_workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == 5,
            max_time=30,
            max_trials=10,
        )
        tasks = Flowcept.db.get_tasks_from_current_workflow()
        for t in tasks:
            if t["activity_id"] == "decorated_static_function":
                assert len(t["used"]) == 1
                assert "arg_0" in t["generated"]
            elif t["activity_id"] == "decorated_static_function2":
                assert len(t["used"]) == 1
                assert "x" in t["used"]
                assert t["generated"]["y"] == 2
            if t["activity_id"] == "decorated_static_function3":
                assert t["used"]["x"] == 3
                assert t["used"]["y"] == 4
                assert t["generated"]["z"] == 5
            elif t["activity_id"] == "decorated_static_function4":
                assert t["used"]["x"] == 3
                assert t["used"]["y"] == 4
                assert t["generated"]["z"] == 6
                assert t["generated"]["w"] == 7

    @patch("sys.argv", ["script_name", "--a", "123", "--b", "abc", "--unknown_arg", "unk", "['a']"])
    def test_argparse(self):
        known_args, unknown_args = parse_args()
        self.assertEqual(known_args.a, 123)
        self.assertEqual(known_args.b, "abc")

        with Flowcept():
            print(Flowcept.current_workflow_id)
            process_arguments_task(known_args, unknown_args)

        task = Flowcept.db.get_tasks_from_current_workflow()[0]
        assert task["status"] == Status.FINISHED.value
        assert task["used"]["known_args"]["a"] == 123
        assert task["used"]["known_args"]["b"] == "abc"
        assert task["used"]["unknown_args"] == ['--unknown_arg', 'unk', "['a']"]

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
                simple_decorated_function(
                    max_tasks=10,  # 100000,
                    check_insertions=False,
                    enable_persistence=False,
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
        threshold = 10 if flowcept.configs.DB_FLUSH_MODE == "offline" else 50  # %
        print("Threshold: ", threshold)
        print("Overheads: " + str(overheads))
        assert all(map(lambda v: v < threshold, overheads))


