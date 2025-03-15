"""Dask plugin module."""

from distributed import Client, WorkerPlugin

from flowcept import WorkflowObject
from flowcept.configs import INSTRUMENTATION
from flowcept.flowceptor.adapters.dask.dask_interceptor import (
    DaskWorkerInterceptor,
)
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


# def _set_workflow_on_scheduler(
#     dask_scheduler=None,
#     workflow_id=None,
#     custom_metadata: dict = None,
#     campaign_id: str = None,
#     workflow_name: str = None,
#     used: dict = None,
# ):
#     custom_metadata = custom_metadata or {}
#     wf_obj = WorkflowObject()
#     wf_obj.workflow_id = workflow_id
#     custom_metadata.update(
#         {
#             "workflow_type": "DaskWorkflow",
#             "scheduler": dask_scheduler.address_safe,
#             "scheduler_id": dask_scheduler.id,
#             "scheduler_pid": dask_scheduler.proc.pid,
#             "clients": len(dask_scheduler.clients),
#             "n_workers": len(dask_scheduler.workers),
#         }
#     )
#     wf_obj.custom_metadata = custom_metadata
#     wf_obj.used = used
#     wf_obj.campaign_id = campaign_id
#     wf_obj.name = workflow_name
#
#     interceptor = BaseInterceptor(plugin_key="dask")
#     interceptor.start(bundle_exec_id=dask_scheduler.address)
#     interceptor.send_workflow_message(wf_obj)
#     interceptor.stop()


def _set_workflow_on_workers(dask_worker, workflow_id, campaign_id=None):
    setattr(dask_worker, "current_workflow_id", workflow_id)
    if campaign_id:
        setattr(dask_worker, "current_campaign_id", campaign_id)


def set_workflow_info_on_workers(dask_client: Client, wf_obj: WorkflowObject):
    """Register the workflow."""
    dask_client.run(_set_workflow_on_workers, workflow_id=wf_obj.workflow_id, campaign_id=wf_obj.campaign_id)


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
            # This is the instrumentation interceptor instance inside each Dask worker process, which is different
            # than the instance in the client process, which might need its own interceptor.
            # Here we are stopping the interceptor we started in the setup_worker method.
            InstrumentationInterceptor.get_instance().stop()
