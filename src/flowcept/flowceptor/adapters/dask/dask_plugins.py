"""Dask plugin module."""

from uuid import uuid4

from dask.distributed import WorkerPlugin, SchedulerPlugin
from distributed import Client

from flowcept import WorkflowObject
from flowcept.flowceptor.adapters.dask.dask_interceptor import (
    DaskSchedulerInterceptor,
    DaskWorkerInterceptor,
)


def _set_workflow_on_scheduler(
    dask_scheduler=None,
    workflow_id=None,
    custom_metadata: dict = None,
    used: dict = None,
):
    custom_metadata = custom_metadata or {}
    wf_obj = WorkflowObject()
    wf_obj.workflow_id = workflow_id
    custom_metadata.update(
        {
            "workflow_type": "DaskWorkflow",
            "scheduler": dask_scheduler.address_safe,
            "scheduler_id": dask_scheduler.id,
            "scheduler_pid": dask_scheduler.proc.pid,
            "clients": len(dask_scheduler.clients),
            "n_workers": len(dask_scheduler.workers),
        }
    )
    wf_obj.custom_metadata = custom_metadata
    wf_obj.used = used
    setattr(dask_scheduler, "current_workflow", wf_obj)


def register_dask_workflow(
    dask_client: Client,
    workflow_id=None,
    custom_metadata: dict = None,
    used: dict = None,
):
    """Register the workflow."""
    workflow_id = workflow_id or str(uuid4())
    dask_client.run_on_scheduler(
        _set_workflow_on_scheduler,
        **{
            "workflow_id": workflow_id,
            "custom_metadata": custom_metadata,
            "used": used,
        },
    )
    return workflow_id


class FlowceptDaskSchedulerAdapter(SchedulerPlugin):
    """Dask schedule adapter."""

    def __init__(self, scheduler):
        self.address = scheduler.address
        self.interceptor = DaskSchedulerInterceptor(scheduler)

    def transition(self, key, start, finish, *args, **kwargs):
        """Get the transition."""
        self.interceptor.callback(key, start, finish, args, kwargs)

    def close(self):
        """Close it."""
        self.interceptor.logger.debug("Going to close scheduler!")
        self.interceptor.stop()


class FlowceptDaskWorkerAdapter(WorkerPlugin):
    """Dask worker adapter."""

    def __init__(self):
        self.interceptor = DaskWorkerInterceptor()

    def setup(self, worker):
        """Set it up."""
        self.interceptor.setup_worker(worker)

    def transition(self, key, start, finish, *args, **kwargs):
        """Run the transition."""
        self.interceptor.callback(key, start, finish, args, kwargs)

    def teardown(self, worker):
        """Tear it down."""
        self.interceptor.logger.debug("Going to close worker!")
        self.interceptor.stop()
