"""Dask plugin module."""

from typing import Optional

from distributed import Client, WorkerPlugin

from flowcept import WorkflowObject
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.configs import INSTRUMENTATION
from flowcept.flowceptor.adapters.dask.dask_interceptor import (
    DaskWorkerInterceptor,
)
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


def _set_workflow_on_workers(dask_worker, workflow_id, campaign_id=None):
    setattr(dask_worker, "current_workflow_id", workflow_id)
    if campaign_id:
        setattr(dask_worker, "current_campaign_id", campaign_id)


def set_workflow_info_on_workers(dask_client: Client, wf_obj: WorkflowObject):
    """Register the workflow."""
    dask_client.run(_set_workflow_on_workers, workflow_id=wf_obj.workflow_id, campaign_id=wf_obj.campaign_id)


def get_flowcept_task() -> Optional[TaskObject]:
    """Get the Flowcept Task Object inside a Worker's task."""
    from distributed import get_worker
    from distributed.worker import thread_state

    worker = get_worker()
    try:
        task_id = thread_state.key if hasattr(thread_state, "key") else None
        if hasattr(worker, "flowcept_tasks") and task_id in worker.flowcept_tasks:
            return worker.flowcept_tasks[task_id]
        else:
            return None
    except Exception as e:
        print(e)
        return None


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
