import os
import pickle
from dask.distributed import WorkerPlugin, SchedulerPlugin


class FlowceptDaskSchedulerPlugin(SchedulerPlugin):
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
                        ferr.write(
                            f"should_get_all_transitions_error={repr(e)}\n"
                        )

            if self._should_get_input:
                try:
                    ts = self.scheduler.tasks[key]
                    if hasattr(ts, "group_key"):
                        line += f" FunctionName={ts.group_key};"
                    if hasattr(ts, "run_spec"):
                        line += FlowceptDaskSchedulerPlugin.get_run_spec_data(
                            ts.run_spec
                        )
                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"FullStateError={repr(e)}\n")

            line += "\n"
            f.write(line)


class FlowceptDaskWorkerPlugin(WorkerPlugin):
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

    def __init__(self):
        self.worker = None
        self.filepath = "worker.log"
        self.error_path = "worker_error.log"
        self._should_get_input = True
        self._should_get_output = True
        super(FlowceptDaskWorkerPlugin, self).__init__()

    def setup(self, worker):
        self.worker = worker
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
                        line += FlowceptDaskWorkerPlugin.get_run_spec_data(
                            ts.run_spec
                        )
                    else:
                        line += "NUM TEM"
                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"\tFullStateError={repr(e)}\n")

            if self._should_get_output and finish == "memory":
                try:
                    if key in self.worker.data.memory:
                        line += f"Worker={self.worker.worker_address}; Key={key}; Output={self.worker.data.memory[key]}\n"
                except Exception as e:
                    with open(self.error_path, "a+") as ferr:
                        ferr.write(f"\should_get_output_error={repr(e)}\n")

            line += "\n"
            f.write(line)
