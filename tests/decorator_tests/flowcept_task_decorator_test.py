import numpy as np
import psutil
import uuid
import random

import pandas as pd
from time import time, sleep

from flowcept import Flowcept
import flowcept
import unittest

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.commons.vocabulary import Status
from flowcept.instrumentation.flowcept_loop import FlowceptLoop
from flowcept.instrumentation.flowcept_task import (
    flowcept_task,
    lightweight_flowcept_task,
)


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
def decorated_static_function2(x):
    return {"y": 2}


@flowcept_task
def decorated_static_function(df: pd.DataFrame):
    return 2


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
            decorated_static_function(df=pd.DataFrame())
            decorated_static_function2(x=1)
            decorated_static_function2(2)

        sleep(1)
        assert assert_by_querying_tasks_until(
            filter={"workflow_id": Flowcept.current_workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == 3,
            max_time=60,
            max_trials=60,
        )

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

    def test_flowcept_loop_types(self):

        with Flowcept():
            items = range(3)
            loop = FlowceptLoop(items=items)
            for _ in loop:
                pass
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(items) + 1

        with Flowcept():
            items = [10, 20, 30]
            loop = FlowceptLoop(items=items)
            for _ in loop:
                pass
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(items) + 1

        with Flowcept():
            items = "abcd"
            loop = FlowceptLoop(items=items)
            for _ in loop:
                pass
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == len(items) + 1

        with Flowcept():
            items = np.array([0.5, 1.0, 1.5])
            loop = FlowceptLoop(items=items, loop_name="our_loop")
            for _ in loop:
                loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id, "activity_id": "our_loop_iteration"})
        assert len(docs) == len(items)
        assert all(d["generated"]["a"] == 1 for d in docs)

        # Unitary range
        with Flowcept():
            epochs_loop = FlowceptLoop(items=range(1, 2), loop_name="epochs_loop",
                                       item_name="epoch")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == 1 + 1
        assert all(d["status"] == "FINISHED" for d in docs)
        sorted_tasks = sorted(docs, key=lambda x: x['started_at'])
        assert sorted_tasks[0]["activity_id"] == "epochs_loop"
        assert sorted_tasks[1]["activity_id"] == "epochs_loop_iteration"
        assert sorted_tasks[1]["used"]["epoch"] == 1

        # Two items
        with Flowcept():
            # unitary lists wont work. also needs to assert that end > init for all tasks
            epochs_loop = FlowceptLoop(items=range(2), loop_name="epochs_loop",
                                       item_name="epoch")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert all(d["status"] == "FINISHED" for d in docs)
        assert len(docs) == len(epochs_loop) + 1
        sorted_tasks = sorted(docs, key=lambda x: x['started_at'])
        assert sorted_tasks[0]["activity_id"] == "epochs_loop"
        iteration_tasks = sorted_tasks[1:]
        for i in range(len(iteration_tasks)):
            t = iteration_tasks[i]
            assert t["parent_task_id"] == sorted_tasks[0]["task_id"]
            assert t["activity_id"] == "epochs_loop_iteration"
            assert t["used"]["i"] == i
            assert t["used"]["epoch"] == i

        # Three items
        with Flowcept():
            # unitary lists wont work. also needs to assert that end > init for all tasks
            epochs_loop = FlowceptLoop(items=3, loop_name="epochs_loop",
                                       item_name="epoch")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert all(d["status"] == "FINISHED" for d in docs)
        assert len(docs) == len(epochs_loop) + 1
        sorted_tasks = sorted(docs, key=lambda x: x['started_at'])
        assert sorted_tasks[0]["activity_id"] == "epochs_loop"
        iteration_tasks = sorted_tasks[1:]
        for i in range(len(iteration_tasks)):
            t = iteration_tasks[i]
            assert t["parent_task_id"] == sorted_tasks[0]["task_id"]
            assert t["activity_id"] == "epochs_loop_iteration"
            assert t["used"]["i"] == i
            assert t["used"]["epoch"] == i

        # Empty list
        with Flowcept():
            # unitary lists wont work. also needs to assert that end > init for all tasks
            epochs_loop = FlowceptLoop(items=[], loop_name="epochs_loop",
                                       item_name="epoch")
            for _ in epochs_loop:
                sleep(TIME_TO_SLEEP)
                epochs_loop.end_iter({"a": 1})
        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == 0


    def test_flowcept_loop_generator(self):
        number_of_epochs = 1
        epochs = range(0, number_of_epochs)
        with Flowcept():
            loop = FlowceptLoop(items=epochs, loop_name="epochs", item_name="epoch")
            for e in loop:
                sleep(TIME_TO_SLEEP)
                loss = random.random()
                print(e, loss)
                loop.end_iter({"loss": loss})

        docs = Flowcept.db.query(filter={"workflow_id": Flowcept.current_workflow_id})
        assert len(docs) == number_of_epochs+1  # 1 (parent_task) + #epochs (sub_tasks)

        iteration_tasks = []
        whole_loop_task = None
        for d in docs:
            if d["activity_id"] == "epochs":
                whole_loop_task = d
                assert whole_loop_task["ended_at"] is not None
                assert whole_loop_task["status"] == Status.FINISHED.value
            else:
                assert d["started_at"] is not None
                assert d["used"]["i"] >= 0
                assert d["generated"]["loss"] > 0
                iteration_tasks.append(d)

        assert len(iteration_tasks) == number_of_epochs
        sorted_iteration_tasks = sorted(iteration_tasks, key=lambda x: x['used']['i'])
        for i in range(len(sorted_iteration_tasks)):
            t = sorted_iteration_tasks[i]
            assert t["used"]["i"] == i
            assert t["used"]["epoch"] == i
            assert t["status"] == Status.FINISHED.value
            assert t["parent_task_id"] == whole_loop_task["task_id"]
