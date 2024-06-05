import flowcept
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor

flowcept.configs.DB_FLUSH_MODE = "offline"
import uuid
from time import sleep
import pandas as pd
from time import time


import flowcept.commons
import flowcept.instrumentation.decorators
from flowcept import FlowceptConsumerAPI

import unittest

from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.instrumentation.decorators.flowcept_task import (
    flowcept_task,
    lightweight_flowcept_task,
)


@lightweight_flowcept_task
def decorated_static_function(df: pd.DataFrame, workflow_id=None):
    return {"y": 2}


def not_decorated_static_function(df: pd.DataFrame, workflow_id=None):
    return {"y": 2}


@flowcept_task
def decorated_static_function2(workflow_id=None):
    return [2]


@flowcept_task
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


class DecoratorTests(unittest.TestCase):
    @flowcept_task
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
            decorated_static_function(pd.DataFrame(), workflow_id=workflow_id)
            decorated_static_function2(workflow_id)
            decorated_static_function3(0.1, workflow_id=workflow_id)
        print(workflow_id)

    def test_decorated_function_simple(
        self, max_tasks=10, start_doc_inserter=True, check_insertions=True
    ):
        max_tasks = 100000
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
            decorated_static_function(pd.DataFrame(), workflow_id=workflow_id)
        t1 = time()
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
            not_decorated_static_function(
                pd.DataFrame(), workflow_id=workflow_id
            )
        t1 = time()
        not_decorated = t1 - t0
        return decorated, not_decorated

    def test_online_offline(self):
        assert flowcept.configs.DB_FLUSH_MODE == "offline"
        self.test_decorated_function_timed()
        flowcept.configs.DB_FLUSH_MODE = "online"
        assert flowcept.configs.DB_FLUSH_MODE == "online"
        flowcept.instrumentation.decorators.instrumentation_interceptor = (
            BaseInterceptor(plugin_key=None)
        )
        self.test_decorated_function_timed()

    def test_decorated_function_timed(self):
        print()
        times = []
        for i in range(10):
            times.append(
                self.test_decorated_function_simple(
                    max_tasks=100000,
                    check_insertions=False,
                    start_doc_inserter=False,
                )
            )
        decorated = [decorated for decorated, not_decorated in times]
        not_decorated = [not_decorated for decorated, not_decorated in times]

        decorated_stats = compute_statistics(decorated)
        not_decorated_stats = compute_statistics(not_decorated)

        overheads = calculate_overheads(decorated_stats, not_decorated_stats)

        n = "00002"
        print(f"#n={n}: Online double buffers; buffer size 100")
        print(f"decorated_{n} = {decorated_stats}")
        print(f"not_decorated_{n} = {not_decorated_stats}")
        print(f"diff_{n} = calculate_diff(decorated_{n}, not_decorated_{n})")
        print(f"'decorated_{n}': diff_{n},")
        print("Overheads: " + str(overheads))

        threshold = (
            5 if flowcept.configs.DB_FLUSH_MODE == "offline" else 50
        )  # %
        assert all(map(lambda v: v < threshold, overheads))
