import os
import pickle
from dask.distributed import WorkerPlugin, SchedulerPlugin


from flowcept.flowceptor.plugins.dask.dask_interceptor import DaskInterceptor


class FlowceptDaskSchedulerPlugin(SchedulerPlugin):

    def __init__(self, scheduler):
        self.address = scheduler.address
        self.interceptor = DaskInterceptor(scheduler)

    def transition(self, key, start, finish, *args, **kwargs):
        self.interceptor.callback(self.address,key, start, finish)


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
