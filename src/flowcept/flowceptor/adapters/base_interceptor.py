"""Base module."""

from abc import abstractmethod
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.configs import (
    ENRICH_MESSAGES,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao.mq_dao_base import MQDao
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.settings_factory import get_settings

from flowcept.flowceptor.telemetry_capture import TelemetryCapture


# TODO :base-interceptor-refactor: :ml-refactor: :code-reorg: :usability:
#  Consider creating a new concept for instrumentation-based 'interception'.
#  These adaptors were made for data observability.
#  Perhaps we should have a BaseAdaptor that would work for both and
#  observability and instrumentation adapters. This would be a major refactor
#  in the code. https://github.com/ORNL/flowcept/issues/109
# class BaseInterceptor(object, metaclass=ABCMeta):
class BaseInterceptor(object):
    """Base interceptor class."""

    def __init__(self, plugin_key=None, kind=None):
        self.logger = FlowceptLogger()
        if plugin_key is not None:  # TODO :base-interceptor-refactor: :code-reorg: :usability:
            self.settings = get_settings(plugin_key)
        else:
            self.settings = None
        self._mq_dao = MQDao.build(adapter_settings=self.settings)
        self._bundle_exec_id = None
        self._interceptor_instance_id = str(id(self))
        self.telemetry_capture = TelemetryCapture()
        self._saved_workflows = set()
        self._generated_workflow_id = False
        self.kind = kind

    def prepare_task_msg(self, *args, **kwargs) -> TaskObject:
        """Prepare a task."""
        raise NotImplementedError()

    def start(self, bundle_exec_id) -> "BaseInterceptor":
        """Start an interceptor."""
        self._bundle_exec_id = bundle_exec_id
        self._mq_dao.init_buffer(self._interceptor_instance_id, bundle_exec_id)
        return self

    def stop(self) -> bool:
        """Stop an interceptor."""
        self._mq_dao.stop(self._interceptor_instance_id, self._bundle_exec_id)

    def observe(self, *args, **kwargs):
        """Oberve data.

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
        if self._mq_dao.buffer is None:
            # TODO :base-interceptor-refactor: :code-reorg: :usability:
            raise Exception(f"This interceptor {id(self)} has never been started!")
        workflow_obj.interceptor_ids = [self._interceptor_instance_id]
        machine_info = self.telemetry_capture.capture_machine_info()
        if machine_info is not None:
            if workflow_obj.machine_info is None:
                workflow_obj.machine_info = dict()
            # TODO :refactor-base-interceptor: we might want to register
            # machine info even when there's no observer
            workflow_obj.machine_info[self._interceptor_instance_id] = machine_info
        if ENRICH_MESSAGES:
            workflow_obj.enrich(self.settings.key if self.settings else None)
        self.intercept(workflow_obj.to_dict())
        return wf_id

    def intercept(self, obj_msg):
        """Intercept it."""
        self._mq_dao.buffer.append(obj_msg)

    # def intercept_appends_only(self, obj_msg):
    #     self._mq_dao.buffer.append(obj_msg)
    #
    # def intercept_appends_with_checks(self, obj_msg):
    #     # self._mq_dao._lock.acquire()
    #     # self._mq_dao.buffer.append(obj_msg)
    #     self._mq_dao.buffer.append(obj_msg)
    #     # if len(self._mq_dao.buffer) >= REDIS_BUFFER_SIZE:
    #     #     self.logger.critical("Redis buffer exceeded, flushing...")
    #     #     self._mq_dao.flush()
    #     # self._mq_dao._lock.release()

    # def intercept(self, obj_msg: Dict):
    #     pass
    #     #self._mq_dao._buffer.append(obj_msg)
    #     #self._mq_dao.publish(obj_msg)
