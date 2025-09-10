from time import time
from typing import Dict, Any
import os
import threading
import random

from flowcept.commons.flowcept_dataclasses.task_object import (
    TaskObject,
)
from flowcept.commons.vocabulary import Status
from flowcept.configs import INSTRUMENTATION_ENABLED, TELEMETRY_ENABLED
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor


class FlowceptTask(object):
    """
    A context manager for capturing and provenance and task telemetry data within the Flowcept
    framework.

    This class encapsulates the lifecycle of a task, recording its start and end times, telemetry,
    and metadata. It integrates with the Flowcept API and Instrumentation Interceptor to
    log task-specific details.

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

    def __init__(
        self,
        task_id: str = None,
        workflow_id: str = None,
        campaign_id: str = None,
        activity_id: str = None,
        agent_id: str = None,
        parent_task_id: str = None,
        used: Dict = None,
        data: Any = None,
        subtype: str = None,
        custom_metadata: Dict = None,
        generated: Dict = None,
        started_at: float = None,
        ended_at: float = None,
        stdout: str = None,
        stderr: str = None,
        status: Status = None,
    ):
        """
        Initializes a FlowceptTask and optionally finalizes it.

        If any of the following optional arguments are provided — `generated`, `ended_at`, `stdout`,
        `stderr`, or `status` — the task will be automatically finalized by calling `end()` during
        initialization. This is useful when the task's outcome is already known at the moment of
        instantiation.

        Parameters
        ----------
        task_id : str, optional
            Unique identifier for the task. Defaults to a generated ID.
        workflow_id : str, optional
            ID of the workflow to which this task belongs.
        campaign_id : str, optional
            ID of the campaign to which this task belongs.
        activity_id : str, optional
            Describes the specific activity this task captures.
        used : Dict, optional
            Metadata about resources or data used during the task.
        data: Any, optional
            Any raw data associated to this task.
        subtype : str, optional
            Optional string categorizing the task subtype.
        custom_metadata : Dict, optional
            Additional user-defined metadata to associate with the task.
        generated : Dict, optional
            Output data generated during the task execution.
        started_at : float, optional
            Timestamp indicating when the task started.
        ended_at : float, optional
            Timestamp indicating when the task ended.
        stdout : str, optional
            Captured standard output from the task.
        stderr : str, optional
            Captured standard error from the task.
        status : Status, optional
            Task completion status. If provided, defaults to Status.FINISHED if unspecified.
        """
        if not INSTRUMENTATION_ENABLED:
            self._ended = True
            return

        self._task = TaskObject()
        self._interceptor = InstrumentationInterceptor.get_instance()

        if TELEMETRY_ENABLED:
            tel = self._interceptor.telemetry_capture.capture()
            self._task.telemetry_at_start = tel

        self._task.activity_id = activity_id
        self._task.started_at = started_at or time()
        self._task.task_id = task_id or self._gen_task_id()
        self._task.workflow_id = workflow_id or Flowcept.current_workflow_id
        self._task.campaign_id = campaign_id or Flowcept.campaign_id
        self._task.parent_task_id = parent_task_id
        self._task.used = used
        self._task.data = data
        self._task.subtype = subtype
        self._task.agent_id = agent_id
        self._task.custom_metadata = custom_metadata

        self._ended = False

        # Check if any of the end-like fields were provided. If yes, end it.
        if any([generated, ended_at, stdout, stderr is not None]):
            self.end(
                generated=generated,
                ended_at=ended_at,
                stdout=stdout,
                stderr=stderr,
                status=status or Status.FINISHED,
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self._ended:
            self.end()

    def _gen_task_id(self):
        pid = os.getpid()
        tid = threading.get_ident()
        rand = random.getrandbits(32)
        return f"{self._task.started_at}_{pid}_{tid}_{rand}"

    def end(
        self,
        generated: Dict = None,
        ended_at: float = None,
        stdout: str = None,
        stderr: str = None,
        data: Any = None,
        custom_metadata: Dict = None,
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
        data: Any, optional
            Any raw data associated to this task.
        custom_metadata : Dict, optional
            Additional user-defined metadata to associate with the task.
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
        if TELEMETRY_ENABLED:
            tel = self._interceptor.telemetry_capture.capture()
            self._task.telemetry_at_end = tel
        if data:
            self._task.data = data
        if custom_metadata:
            self._task.custom_metadata = custom_metadata
        self._task.ended_at = ended_at or time()
        self._task.status = status
        self._task.stderr = stderr
        self._task.stdout = stdout
        self._task.generated = generated
        if self._interceptor._mq_dao.buffer is None:
            raise Exception("Did you start Flowcept?")
        self._interceptor.intercept(self._task.to_dict())
        self._ended = True

    def send(self):
        """
        Finalizes and sends the task data if not already ended.

        This method acts as a simple alias for finalizing the task without requiring additional
        arguments. It sends the task object to the interceptor for capture and marks it as ended
        to prevent multiple submissions.
        """
        if not self._ended:
            if self._interceptor._mq_dao.buffer is None:
                raise Exception("Did you start Flowcept?")
            self._task.ended_at = self._task.started_at  # message sents are not going to be analyzed for task duration
            self._interceptor.intercept(self._task.to_dict())
            self._ended = True
