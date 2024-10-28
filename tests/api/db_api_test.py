import unittest
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept import Flowcept, WorkflowObject
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.flowceptor.telemetry_capture import TelemetryCapture


class OurObject:
    def __init__(self):
        self.a = 1
        self.b = 2

    def __str__(self):
        return f"It worked! {self.a} {self.b}"


class DBAPITest(unittest.TestCase):
    def test_wf_dao(self):
        workflow1_id = str(uuid4())
        wf1 = WorkflowObject()
        wf1.workflow_id = workflow1_id

        assert Flowcept.db.insert_or_update_workflow(wf1)

        wf1.custom_metadata = {"test": "abc"}
        assert Flowcept.db.insert_or_update_workflow(wf1)

        wf_obj = Flowcept.db.get_workflow(workflow_id=workflow1_id)
        assert wf_obj is not None
        print(wf_obj)

        wf2_id = str(uuid4())
        print(wf2_id)

        wf2 = WorkflowObject()
        wf2.workflow_id = wf2_id

        tel = TelemetryCapture()
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf2.interceptor_ids = ["123"]
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf2.interceptor_ids = ["1234"]
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow(wf2_id)
        assert len(wf_obj.interceptor_ids) == 2
        wf2.machine_info = {"123": tel.capture_machine_info()}
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow(wf2_id)
        assert wf_obj
        wf2.machine_info = {"1234": tel.capture_machine_info()}
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow(wf2_id)
        assert len(wf_obj.machine_info) == 2

    def test_save_blob(self):
        import pickle

        obj = pickle.dumps(OurObject())

        obj_id = Flowcept.db.save_object(object=obj, save_data_in_collection=True)
        print(obj_id)

        obj_docs = Flowcept.db.query(
            filter={"object_id": obj_id}, type="object"
        )
        loaded_obj = pickle.loads(obj_docs[0]["data"])
        assert type(loaded_obj) == OurObject

    def test_dump(self):
        wf_id = str(uuid4())

        c0 = Flowcept.db._dao.count()

        for i in range(10):
            t = TaskObject()
            t.workflow_id = wf_id
            t.task_id = str(uuid4())
            Flowcept.db.insert_or_update_task(t)

        _filter = {"workflow_id": wf_id}
        assert Flowcept.db.dump_to_file(
            filter=_filter,
        )
        assert Flowcept.db.dump_to_file(filter=_filter, should_zip=True)
        assert Flowcept.db.dump_to_file(
            filter=_filter, output_file="dump_test.json"
        )

        Flowcept.db._dao.delete_with_filter(_filter)
        c1 = Flowcept.db._dao.count()
        assert c0 == c1

    def test_dbapi_singleton(self):
        db1 = DBAPI()
        db2 = DBAPI()
        self.assertIs(db1, db2)

        db1.v = "test_val"
        self.assertEqual(db2.v, "test_val")
