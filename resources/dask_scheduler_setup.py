from flowcept import FlowceptDaskSchedulerPlugin


def dask_setup(scheduler):
    scheduler_plugin = FlowceptDaskSchedulerPlugin(scheduler)
    scheduler.add_plugin(scheduler_plugin)
