"""Base Interceptor module."""

from abc import abstractmethod
from typing import Dict, List
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.configs import (
    ENRICH_MESSAGES,
    TELEMETRY_ENABLED,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.settings_factory import get_settings


# TODO :base-interceptor-refactor: :ml-refactor: :code-reorg: :usability:
#  Consider creating a new concept for instrumentation-based 'interception'.
#  These adaptors were made for data observability.
#  Perhaps we should have a BaseAdaptor that would work for both and
#  observability and instrumentation adapters. This would be a major refactor
#  in the code. https://github.com/ORNL/flowcept/issues/109
# class BaseInterceptor(object, metaclass=ABCMeta):
class BaseInterceptor(object):
    """Base interceptor class."""

    @staticmethod
    def build(kind: str) -> "BaseInterceptor":
        """Build the Interceptor."""
        # TODO consider making singleton for all, just for standardization
        if kind == "mlflow":
            from flowcept.flowceptor.adapters.mlflow.mlflow_interceptor import MLFlowInterceptor

            return MLFlowInterceptor()
        elif kind == "tensorboard":
            from flowcept.flowceptor.adapters.tensorboard.tensorboard_interceptor import TensorboardInterceptor

            return TensorboardInterceptor()

        elif kind == "broker_mqtt":
            from flowcept.flowceptor.adapters.brokers.mqtt_interceptor import MQTTBrokerInterceptor

            return MQTTBrokerInterceptor()
        elif kind == "dask_worker":
            from flowcept.flowceptor.adapters.dask.dask_interceptor import DaskWorkerInterceptor

            return DaskWorkerInterceptor()
        elif kind in "dask":
            # This is dask's client interceptor. We essentially use it to store the dask workflow.
            # That's why we don't need another special interceptor and we can reuse the instrumentation one.
            from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor

            return InstrumentationInterceptor.get_instance()
        elif kind == "instrumentation":
            from flowcept.flowceptor.adapters.instrumentation_interceptor import InstrumentationInterceptor

            return InstrumentationInterceptor.get_instance()
        else:
            raise NotImplementedError

    def __init__(self, plugin_key=None, kind=None):
        self.logger = FlowceptLogger()
        # self.logger.debug(f"Starting Interceptor{id(self)} at {time()}")
        self.plugin_key = plugin_key
        if self.plugin_key is not None:  # TODO :base-interceptor-refactor: :code-reorg: :usability:
            self.settings = get_settings(self.plugin_key)
        else:
            self.settings = None
        self._mq_dao = MQDao.build(adapter_settings=self.settings)
        self._bundle_exec_id = None
        self.started = False
        self._interceptor_instance_id = str(id(self))

        if TELEMETRY_ENABLED:
            from flowcept.flowceptor.telemetry_capture import TelemetryCapture

            self.telemetry_capture = TelemetryCapture()
        else:
            self.telemetry_capture = None

        self._saved_workflows = set()
        self._generated_workflow_id = False
        self.kind = kind

    def prepare_task_msg(self, *args, **kwargs) -> TaskObject:
        """Prepare a task."""
        raise NotImplementedError()

    def start(self, bundle_exec_id, check_safe_stops: bool = True) -> "BaseInterceptor":
        """Start an interceptor."""
        if not self.started:
            self._bundle_exec_id = bundle_exec_id
            self._mq_dao.init_buffer(self._interceptor_instance_id, bundle_exec_id, check_safe_stops)
            self.started = True
        return self

    def stop(self, check_safe_stops: bool = True):
        """Stop an interceptor."""
        self._mq_dao.stop(
            interceptor_instance_id=self._interceptor_instance_id,
            check_safe_stops=check_safe_stops,
            bundle_exec_id=self._bundle_exec_id,
        )
        self.started = False

    def observe(self, *args, **kwargs):
        """Observe data.

        This method implements data observability over a data channel (e.g., a
        file, a DBMS, an MQ)
        """
        raise NotImplementedError()

    @abstractmethod
    def callback(self, *args, **kwargs):
        """Implement a callback.

        Method that implements the logic that decides what do to when a change
        (e.g., task state change) is identified. If it's an interesting
        change, it calls self.intercept; otherwise, let it go....
        """
        raise NotImplementedError()

    def send_workflow_message(self, workflow_obj: WorkflowObject):
        """Send workflow."""
        wf_id = workflow_obj.workflow_id or str(uuid4())
        workflow_obj.workflow_id = wf_id
        if wf_id in self._saved_workflows:
            return
        self._saved_workflows.add(wf_id)
        if not self._mq_dao.started:
            # TODO :base-interceptor-refactor: :code-reorg: :usability:
            raise Exception(f"This interceptor {id(self)} has never been started!")
        workflow_obj.interceptor_ids = [self._interceptor_instance_id]
        if self.telemetry_capture:
            machine_info = self.telemetry_capture.capture_machine_info()
            if workflow_obj.machine_info is None:
                workflow_obj.machine_info = dict()
            # TODO :refactor-base-interceptor: we might want to register
            # machine info even when there's no observer
            workflow_obj.machine_info[self._interceptor_instance_id] = machine_info
        if ENRICH_MESSAGES:
            workflow_obj.enrich(self.settings.key if self.settings else None)
        self.intercept(workflow_obj.to_dict())
        return wf_id

    def intercept(self, obj_msg: Dict):
        """Intercept a message."""
        self._mq_dao.buffer.append(obj_msg)

    def intercept_many(self, obj_messages: List[Dict]):
        """Intercept a list of messages."""
        self._mq_dao.buffer.extend(obj_messages)

    def set_buffer(self, buffer):
        """Redefine the interceptor's buffer. Use it very carefully."""
        self._mq_dao.buffer = buffer
