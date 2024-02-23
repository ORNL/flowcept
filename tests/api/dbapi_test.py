import unittest
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.flowceptor.telemetry_capture import TelemetryCapture


class WorkflowDBTest(unittest.TestCase):
    def test_wf_dao(self):
        dbapi = DBAPI()
        workflow1_id = str(uuid4())
        wf1 = WorkflowObject()
        wf1.workflow_id = workflow1_id

        assert dbapi.insert_or_update_workflow(wf1)

        wf1.custom_metadata = {"test": "abc"}
        assert dbapi.insert_or_update_workflow(wf1)

        wf_obj = dbapi.get_workflow(workflow_id=workflow1_id)
        assert wf_obj is not None
        print(wf_obj)

        wf2_id = str(uuid4())
        print(wf2_id)

        wf2 = WorkflowObject(workflow_id=wf2_id)

        tel = TelemetryCapture()
        assert dbapi.insert_or_update_workflow(wf2)
        wf2.interceptor_ids = ["123"]
        assert dbapi.insert_or_update_workflow(wf2)
        wf2.interceptor_ids = ["1234"]
        assert dbapi.insert_or_update_workflow(wf2)
        wf_obj = dbapi.get_workflow(wf2_id)
        assert len(wf_obj.interceptor_ids) == 2
        wf2.machine_info = {"123": tel.capture_machine_info()}
        assert dbapi.insert_or_update_workflow(wf2)
        wf_obj = dbapi.get_workflow(wf2_id)
        assert wf_obj
        wf2.machine_info = {"1234": tel.capture_machine_info()}
        assert dbapi.insert_or_update_workflow(wf2)
        wf_obj = dbapi.get_workflow(wf2_id)
        assert len(wf_obj.machine_info) == 2

    def test_dump(self):
        dbapi = DBAPI()
        wf_id = str(uuid4())

        c0 = dbapi._dao.count()

        for i in range(10):
            t = TaskObject()
            t.workflow_id = wf_id
            t.task_id = str(uuid4())
            dbapi.insert_or_update_task(t)

        _filter = {"workflow_id": wf_id}
        assert dbapi.dump_to_file(
            filter=_filter,
        )
        assert dbapi.dump_to_file(filter=_filter, should_zip=True)
        assert dbapi.dump_to_file(
            filter=_filter, output_file="dump_test.json"
        )

        dbapi._dao.delete_with_filter(_filter)
        c1 = dbapi._dao.count()
        assert c0 == c1
