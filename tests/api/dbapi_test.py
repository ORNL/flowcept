import unittest
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.task_message import TaskMessage
from flowcept.commons.flowcept_dataclasses.telemetry import Telemetry
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.flowceptor.telemetry_capture import TelemetryCapture


class WorkflowDBTest(unittest.TestCase):
    def test_wf_dao(self):
        dbapi = DBAPI()
        wf1 = str(uuid4())

        assert dbapi.insert_or_update_workflow(workflow_id=wf1)

        assert dbapi.insert_or_update_workflow(
            workflow_id=wf1, workflow_info={"test": "abc"}
        )

        wfdata = dbapi.get_workflow(workflow_id=wf1)
        assert wfdata is not None
        print(wfdata)

        wf2 = str(uuid4())
        print(wf2)

        tel = TelemetryCapture()
        assert dbapi.insert_or_update_workflow(workflow_id=wf2)
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2, workflow_info={"interceptor_id": "123"}
        )
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2, workflow_info={"interceptor_id": "1234"}
        )
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2,
            workflow_info={
                "machine_info": {"123": tel.capture_machine_info()}
            },
        )
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2,
            workflow_info={
                "machine_info": {"1234": tel.capture_machine_info()}
            },
        )
        wfdata = dbapi.get_workflow(workflow_id=wf2)
        print(wfdata)
        assert wfdata is not None

    def test_dump(self):
        dbapi = DBAPI()
        wf_id = str(uuid4())

        c0 = dbapi._dao.count()

        for i in range(10):
            t = TaskMessage()
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
