import numpy as np
from time import sleep
from time import time


def computation1(x):
    print(f"Computation 1, going to sleep {x} s.")
    sleep(x)
    return x * 2


def computation2(x):
    print(f"Computation 2, going to sleep {x} s.")
    sleep(x)
    return x + x


def computation3(x):
    print(f"Computation 3, going to sleep {x} s.")
    sleep(x)
    return x + 2


def two_outputs():
    return 1, 2


import os
import pickle
from dask.distributed import Client, LocalCluster
from dask.distributed import WorkerPlugin, SchedulerPlugin


class MyWorkerPlugin(WorkerPlugin):
    @staticmethod
    def get_run_spec_data(run_spec):
        line = ""
        if hasattr(run_spec, "function"):
            line += f", function_call={pickle.loads(run_spec.function)}"
        if hasattr(run_spec, "args") and run_spec.args:
            line += f", function_args={pickle.loads(run_spec.args)}"
        if hasattr(run_spec, "kwargs") and run_spec.kwargs:
            line += f", function_kwargs={pickle.loads(run_spec.kwargs)}"
        return line

    def setup(self, worker):
        self.worker = worker
        self.filepath = "worker.log"
        self.error_path = "worker_error.log"

        self._should_get_input = True
        self._should_get_output = True

        for f in [self.filepath, self.error_path]:
            if os.path.exists(f):
                os.remove(f)

    def transition(self, key, start, finish, *args, **kwargs):
        with open(self.filepath, "a+") as f:
            line = ""
            if self._should_get_input and start == "released":
                line = f"Worker={self.worker.worker_address}; Key={key}; Start={start}; Finish={finish};"
                try:
                    ts = self.worker.state.tasks[key]
                    if hasattr(ts, "run_spec"):
                        line += MyWorkerPlugin.get_run_spec_data(ts.run_spec)

                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"\tFullStateError={e}\n")

            if self._should_get_output and finish == "memory":
                try:
                    if key in self.worker.data.memory:
                        line += f"Worker={self.worker.worker_address}; Key={key}; Output={self.worker.data.memory[key]}\n"
                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"\should_get_output_error={e}\n")

            line += "\n"
            f.write(line)


class MySchedulerPlugin(SchedulerPlugin):
    @staticmethod
    def get_run_spec_data(run_spec):
        line = f""
        if run_spec.get("function"):
            line += (
                f", function_call={pickle.loads(run_spec.get('function'))}"
            )
        if run_spec.get("args"):
            line += f", function_args={pickle.loads(run_spec.get('args'))}"
        if run_spec.get("kwargs"):
            line += (
                f", function_kwargs={pickle.loads(run_spec.get('kwargs'))}"
            )
        return line

    def __init__(self, scheduler):
        self.scheduler = scheduler
        self.filepath = "scheduler.log"
        self.error_path = "scheduler_error.log"
        self._should_get_all_transitions = True
        self._should_get_input = True

        for f in [self.filepath, self.error_path]:
            if os.path.exists(f):
                os.remove(f)

    def transition(self, key, start, finish, *args, **kwargs):
        with open(self.filepath, "a+") as f:

            line = ""
            if self._should_get_all_transitions:
                line += (
                    f"Key={key}, start={start}, finish={finish}, args={args}"
                )
                try:
                    if kwargs:
                        if kwargs.get("type"):
                            kwargs["type"] = pickle.loads(kwargs.get("type"))
                        line += f", kwargs={kwargs}; "
                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"should_get_all_transitions_error={e}\n")

            if self._should_get_input:
                try:
                    ts = self.scheduler.tasks[key]
                    if hasattr(ts, "group_key"):
                        line += f" FunctionName={ts.group_key};"
                    if hasattr(ts, "run_spec"):
                        line += MySchedulerPlugin.get_run_spec_data(
                            ts.run_spec
                        )
                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"FullStateError={e}\n")

            line += "\n"
            f.write(line)


if __name__ == "__main__":

    cluster = LocalCluster(n_workers=1)
    scheduler = cluster.scheduler
    client = Client(scheduler.address)

    scheduler.add_plugin(MySchedulerPlugin(scheduler))
    client.register_worker_plugin(MyWorkerPlugin())
    client.scheduler_info()

    i1 = np.random.rand()
    print("Inputs", i1)
    o1 = client.submit(computation1, i1)
    o2 = client.submit(computation2, o1)
