from dask.distributed import WorkerPlugin, SchedulerPlugin


from flowcept.flowceptor.adapters.dask.dask_interceptor import (
    DaskSchedulerInterceptor,
    DaskWorkerInterceptor,
)


class FlowceptDaskSchedulerAdapter(SchedulerPlugin):
    def __init__(self, scheduler):
        self.address = scheduler.address
        self.interceptor = DaskSchedulerInterceptor(scheduler)

    def transition(self, key, start, finish, *args, **kwargs):
        self.interceptor.callback(key, start, finish, args, kwargs)

    def close(self):
        self.interceptor.logger.debug("Going to close scheduler!")
        self.interceptor.stop()


class FlowceptDaskWorkerAdapter(WorkerPlugin):
    def __init__(self):
        self.interceptor = DaskWorkerInterceptor()

    def setup(self, worker):
        self.interceptor.setup_worker(worker)

    def transition(self, key, start, finish, *args, **kwargs):
        self.interceptor.callback(key, start, finish, args, kwargs)

    def teardown(self, worker):
        self.interceptor.logger.debug("Going to close worker!")
        self.interceptor.stop()
