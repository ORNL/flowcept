"""Dask plugin module."""

from uuid import uuid4

from dask.distributed import WorkerPlugin, SchedulerPlugin
from distributed import Client, Scheduler

from flowcept import WorkflowObject
from flowcept.configs import INSTRUMENTATION
from flowcept.flowceptor.adapters.dask.dask_interceptor import (
    DaskSchedulerInterceptor,
    DaskWorkerInterceptor,
)
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


def _set_workflow_on_scheduler(
    dask_scheduler=None,
    workflow_id=None,
    custom_metadata: dict = None,
    campaign_id: str = None,
    workflow_name: str = None,
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
    wf_obj.campaign_id = campaign_id
    wf_obj.name = workflow_name
    setattr(dask_scheduler, "current_workflow", wf_obj)


def register_dask_workflow(
    dask_client: Client,
    workflow_id=None,
    campaign_id=None,
    workflow_name=None,
    custom_metadata: dict = None,
    used: dict = None,
):
    """Register the workflow."""
    # TODO: consider moving this to inside Flowcept controller
    workflow_id = workflow_id or str(uuid4())
    dask_client.run_on_scheduler(
        _set_workflow_on_scheduler,
        **{
            "workflow_id": workflow_id,
            "custom_metadata": custom_metadata,
            "used": used,
            "workflow_name": workflow_name,
            "campaign_id": campaign_id,
        },
    )
    return workflow_id


class FlowceptDaskSchedulerAdapter(SchedulerPlugin):
    """Dask schedule adapter."""

    def __init__(self):
        self.interceptor = None

    def start(self, scheduler: Scheduler) -> None:
        """Run this when scheduler starts."""
        self.interceptor = DaskSchedulerInterceptor(scheduler)

    def transition(self, key, start, finish, *args, **kwargs):
        """Get the transition."""
        self.interceptor.callback(key, start, finish, args, kwargs)

    async def close(self):
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

        instrumentation = INSTRUMENTATION.get("enabled", False)
        if instrumentation:
            InstrumentationInterceptor.get_instance().stop()
