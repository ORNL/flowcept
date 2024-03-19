import uuid
from abc import ABCMeta, abstractmethod
from typing import Union

from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.commons.utils import get_utc_now
from flowcept.configs import (
    settings,
    FLOWCEPT_USER,
    SYS_NAME,
    NODE_NAME,
    LOGIN_NAME,
    PUBLIC_IP,
    PRIVATE_IP,
    CAMPAIGN_ID,
    HOSTNAME,
    EXTRA_METADATA,
    ENRICH_MESSAGES,
    ENVIRONMENT_ID,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.daos.mq_dao import MQDao
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.settings_factory import get_settings

from flowcept.flowceptor.telemetry_capture import TelemetryCapture

from flowcept.version import __version__


# TODO :base-interceptor-refactor: :ml-refactor: :code-reorg: :usability:
#  Consider creating a new concept for instrumentation-based 'interception'.
#  These adaptors were made for data observability.
#  Perhaps we should have a BaseAdaptor that would work for both and
#  observability and instrumentation adapters. This would be a major refactor
#  in the code. https://github.com/ORNL/flowcept/issues/109
# class BaseInterceptor(object, metaclass=ABCMeta):
class BaseInterceptor(object):
    def __init__(self, plugin_key):
        self.logger = FlowceptLogger()
        if (
            plugin_key is not None
        ):  # TODO :base-interceptor-refactor: :code-reorg: :usability:
            self.settings = get_settings(plugin_key)
        else:
            self.settings = None
        self._mq_dao = MQDao(adapter_settings=self.settings)
        # self._db_api = DBAPI()
        self._bundle_exec_id = None
        self._interceptor_instance_id = str(id(self))
        self.telemetry_capture = TelemetryCapture()
        self._saved_workflows = set()
        self._generated_workflow_id = False

    def prepare_task_msg(self, *args, **kwargs) -> TaskObject:
        raise NotImplementedError()

    def start(self, bundle_exec_id) -> "BaseInterceptor":
        """
        Starts an interceptor
        :return:
        """
        self._bundle_exec_id = bundle_exec_id
        self._mq_dao.start_time_based_flushing(
            self._interceptor_instance_id, bundle_exec_id
        )
        return self

    def stop(self) -> bool:
        """
        Gracefully stops an interceptor
        :return:
        """
        self._mq_dao.stop_time_based_flushing(
            self._interceptor_instance_id, self._bundle_exec_id
        )
        self.telemetry_capture.shutdown_gpu_telemetry()

    def observe(self, *args, **kwargs):
        """
        This method implements data observability over a data channel
         (e.g., a file, a DBMS, an MQ)
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    def callback(self, *args, **kwargs):
        """
        Method that implements the logic that decides what do to when a change
         (e.g., task state change) is identified.
        If it's an interesting change, it calls self.intercept; otherwise,
        let it go....
        """
        raise NotImplementedError()

    def send_workflow_message(self, workflow_obj: WorkflowObject):
        wf_id = workflow_obj.workflow_id
        if wf_id is None:
            self.logger.warning(
                f"Workflow_id is empty, we can't save this workflow_obj: {workflow_obj}"
            )
            return
        if wf_id in self._saved_workflows:
            return
        self._saved_workflows.add(wf_id)
        if (  # NO MQ
            self._mq_dao._buffer is None
        ):  # TODO :base-interceptor-refactor: :code-reorg: :usability:
            raise Exception(
                f"This interceptor {id(self)} has never been started!"
            )
        workflow_obj.interceptor_ids = [self._interceptor_instance_id]
        machine_info = self.telemetry_capture.capture_machine_info()
        if machine_info is not None:
            if workflow_obj.machine_info is None:
                workflow_obj.machine_info = dict()
            # TODO :refactor-base-interceptor: we might want to register machine info even when there's no observer
            workflow_obj.machine_info[
                self._interceptor_instance_id
            ] = machine_info

        self._mq_dao.publish(workflow_obj)

    def intercept(self, obj_msg: Union[TaskObject, WorkflowObject]):
        self._mq_dao.publish(obj_msg)
        return
