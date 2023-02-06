import os
import pickle
from dask.distributed import WorkerPlugin, SchedulerPlugin


from flowcept.flowceptor.plugins.dask.dask_interceptor import (
    DaskSchedulerInterceptor,
    DaskWorkerInterceptor,
)


class FlowceptDaskSchedulerPlugin(SchedulerPlugin):
    def __init__(self, scheduler):
        self.address = scheduler.address
        self.interceptor = DaskSchedulerInterceptor(scheduler)

    def transition(self, key, start, finish, *args, **kwargs):
        self.interceptor.callback(key, start, finish, args, kwargs)


class FlowceptDaskWorkerPlugin(WorkerPlugin):
    def __init__(self):
        self.interceptor = DaskWorkerInterceptor()

    def setup(self, worker):
        self.interceptor.setup_worker(worker)

    def transition(self, key, start, finish, *args, **kwargs):
        self.interceptor.callback(key, start, finish, args, kwargs)
