from time import time
from typing import Dict

from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.configs import INSTRUMENTATION_ENABLED
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


class FlowceptTask(object):
    """
    A context manager for capturing and provenance and task telemetry data within the Flowcept
    framework.

    This class encapsulates the lifecycle of a task, recording its start and end times, telemetry,
    and metadata. It integrates with the Flowcept API and Instrumentation Interceptor to
    log task-specific details.

    Parameters
    ----------
    task_id : str, optional
        Unique identifier for the task. If not provided, it defaults to the current timestamp.
    workflow_id : str, optional
        ID of the workflow to which this task belongs. Defaults to the current workflow ID from
        Flowcept.
    campaign_id : str, optional
        ID of the campaign to which this task belongs. Defaults to the current campaign ID from
        Flowcept.
    used : Dict, optional
        Metadata about the resources or data used during the task execution.
    custom_metadata : Dict, optional
        User-defined metadata associated with the task.

    Methods
    -------
    __enter__()
        Sets up the task context.
    __exit__(exc_type, exc_val, exc_tb)
        Ends the task context, ensuring telemetry and metadata are recorded.
    end(generated=None, ended_at=None, stdout=None, stderr=None, status=Status.FINISHED)
        Finalizes the task, capturing telemetry, status, and other details.

    Notes
    -----
    If instrumentation is disabled (`INSTRUMENTATION_ENABLED` is False), the methods in this class
    are no-ops, and no data is captured.
    """

    if INSTRUMENTATION_ENABLED:
        _interceptor = InstrumentationInterceptor.get_instance()

    def __init__(
        self,
        task_id: str = None,
        workflow_id: str = None,
        campaign_id: str = None,
        activity_id: str = None,
        used: Dict = None,
        custom_metadata: Dict = None,
    ):
        if not INSTRUMENTATION_ENABLED:
            self._ended = True
            return
        self._task = TaskObject()
        self._task.telemetry_at_start = FlowceptTask._interceptor.telemetry_capture.capture()
        self._task.activity_id = activity_id
        self._task.started_at = time()
        self._task.task_id = task_id or str(self._task.started_at)
        self._task.workflow_id = workflow_id or Flowcept.current_workflow_id
        self._task.campaign_id = campaign_id or Flowcept.campaign_id
        self._task.used = used
        self._task.custom_metadata = custom_metadata
        self._ended = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._ended:
            self.end()

    def end(
        self,
        generated: Dict = None,
        ended_at: float = None,
        stdout: str = None,
        stderr: str = None,
        status: Status = Status.FINISHED,
    ):
        """
        Finalizes the task by capturing its end state, telemetry, and status.

        This method records the task's ending telemetry data, status, and any outputs or errors.
        It also sends the task data to the instrumentation interceptor for logging or further
        processing.

        Parameters
        ----------
        generated : Dict, optional
            Metadata or data generated during the task's execution. Defaults to None.
        ended_at : float, optional
            Timestamp indicating when the task ended. If not provided, defaults to the current time.
        stdout : str, optional
            Standard output captured during the task's execution. Defaults to None.
        stderr : str, optional
            Standard error captured during the task's execution. Defaults to None.
        status : Status, optional
            Status of the task at the time of completion. Defaults to `Status.FINISHED`.

        Notes
        -----
        If instrumentation is disabled (`INSTRUMENTATION_ENABLED` is False), this method performs
        no actions.
        """
        if not INSTRUMENTATION_ENABLED:
            return
        self._task.telemetry_at_end = FlowceptTask._interceptor.telemetry_capture.capture()
        self._task.ended_at = ended_at or time()
        self._task.status = status
        self._task.stderr = stderr
        self._task.stdout = stdout
        self._task.generated = generated
        FlowceptTask._interceptor.intercept(self._task.to_dict())
        self._ended = True
