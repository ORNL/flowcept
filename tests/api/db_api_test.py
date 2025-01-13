import unittest
from uuid import uuid4

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept import Flowcept, WorkflowObject
from flowcept.configs import MONGO_ENABLED
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

        wf_obj = Flowcept.db.get_workflow_object(workflow_id=workflow1_id)
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
        wf_obj = Flowcept.db.get_workflow_object(wf2_id)
        if MONGO_ENABLED:
            # TODO: note that some of these tests currently only work on MongoDB because
            #  updating is not yet implemented in LMDB
            assert len(wf_obj.interceptor_ids) == 2
        wf2.machine_info = {"123": tel.capture_machine_info()}
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow_object(wf2_id)
        assert wf_obj
        wf2.machine_info = {"1234": tel.capture_machine_info()}
        assert Flowcept.db.insert_or_update_workflow(wf2)
        wf_obj = Flowcept.db.get_workflow_object(wf2_id)
        if MONGO_ENABLED:
            assert len(wf_obj.machine_info) == 2

    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_save_blob(self):
        import pickle

        obj = pickle.dumps(OurObject())

        obj_id = Flowcept.db.save_or_update_object(object=obj, save_data_in_collection=True)
        print(obj_id)

        obj_docs = Flowcept.db.query(filter={"object_id": obj_id}, collection="objects")
        loaded_obj = pickle.loads(obj_docs[0]["data"])
        assert type(loaded_obj) == OurObject

    @unittest.skip("Test only for dev.")
    def test_tasks_recursive(self):
        mapping = {
            "activity_id": {
                "epochs_loop_iteration": [
                    "{'epoch': task['used']['epoch']}",
                    "{'model_train': ancestors[task['task_id']][-1]['task_id']}"
                ],
                "train_batch_iteration": [
                    "{'train_batch': task['used']['i'], 'train_data_path': ancestors[task['task_id']][0]['used']['train_data_path'], 'train_batch_size': ancestors[task['task_id']][0]['used']['batch_size'] }",
                    "{'epoch': ancestors[task['task_id']][-1]['used']['epoch']}"
                ],
                "eval_batch_iteration": [
                    "{'eval_batch': task['used']['i'], 'eval_data_path': ancestors[task['task_id']][0]['used']['val_data_path'], 'train_batch_size': ancestors[task['task_id']][0]['used']['eval_batch_size'] }",
                    "{'epoch': ancestors[task['task_id']][-1]['used']['epoch']}"
                ],
            },
            "subtype": {
                "parent_forward": [
                    "{'model': task['activity_id']}",
                    "ancestors[task['task_id']][-1]['custom_provenance_id']"
                ],
                "child_forward": [
                    "{'module': task['activity_id']}",
                    "ancestors[task['task_id']][-1]['custom_provenance_id']"
                ]
            }
        }
        d = Flowcept.db._dao().get_tasks_recursive('e9a3b567-cb56-4884-ba14-f137c0260191', mapping=mapping)


    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_dump(self):
        wf_id = str(uuid4())

        c0 = Flowcept.db._dao().count_tasks()

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
        assert Flowcept.db.dump_to_file(filter=_filter, output_file="dump_test.json")

        Flowcept.db._dao().delete_tasks_with_filter(_filter)
        c1 = Flowcept.db._dao().count_tasks()
        assert c0 == c1

