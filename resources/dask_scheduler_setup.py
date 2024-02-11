from flowcept import FlowceptDaskSchedulerAdapter


def dask_setup(scheduler):
    scheduler_plugin = FlowceptDaskSchedulerAdapter(scheduler)
    scheduler.add_plugin(scheduler_plugin)
