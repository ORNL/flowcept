import unittest
import uuid

import pytest
from pathlib import Path
from time import sleep

from flowcept.commons.vocabulary import Status
from flowcept import Flowcept, FlowceptTask
from flowcept import configs


class ExplicitTaskTest(unittest.TestCase):

    def test_task_capture(self):
        with Flowcept():
            used_args = {"a": 1}
            with FlowceptTask(used=used_args) as t:
                t.end(generated={"b": 2})

        task = Flowcept.db.get_tasks_from_current_workflow()[0]
        assert task["used"]["a"] == 1
        assert task["generated"]["b"] == 2
        assert task["status"] == Status.FINISHED.value

        with Flowcept():
            used_args = {"a": 1}
            with FlowceptTask(used=used_args):
                pass

        task = Flowcept.db.get_tasks_from_current_workflow()[0]
        assert task["used"]["a"] == 1
        assert task["status"] == Status.FINISHED.value
        assert "generated" not in task

    def test_explicit_task_custom_metadata_non_serializable_is_sanitized(self):
        with Flowcept():
            with FlowceptTask(used={"a": 1}, custom_metadata={"non_serializable_obj": object()}) as task_ctx:
                task_ctx.end(generated={"b": 2})

            tasks = [msg for msg in Flowcept.buffer if isinstance(msg, dict) and msg.get("type") == "task"]
            assert tasks
            task = tasks[-1]
        value = task["custom_metadata"]["non_serializable_obj"]
        assert isinstance(value, str)
        assert value.startswith("object_instance_id_")

    @pytest.mark.safeoffline
    def test_custom_tasks(self):
        if not configs.DUMP_BUFFER_ENABLED:
            self.skipTest("Skipping test_custom_tasks because project.dump_buffer.enabled is false.")

        flowcept = Flowcept(start_persistence=False, save_workflow=True, workflow_name="MyFirstWorkflow").start()

        agent1 = str(uuid.uuid4())
        t1 = FlowceptTask(activity_id="super_func1", used={"x":1}, agent_id=agent1, tags=["tag1"]).send()

        with FlowceptTask(activity_id="super_func2", used={"y": 1}, agent_id=agent1, tags=["tag2"]) as t2:
            sleep(0.5)
            t2.end(generated={"o": 3})

        t3 = FlowceptTask(activity_id="super_func3", used={"z": 1}, agent_id=agent1, tags=["tag3"])
        sleep(0.1)
        t3.end(generated={"w":1})

        workflow_id = Flowcept.current_workflow_id
        flowcept.stop()

        read_args = {"file_path": configs.DUMP_BUFFER_PATH}
        if configs.APPEND_WORKFLOW_ID_TO_PATH or configs.APPEND_ID_TO_PATH:
            read_args["consolidate"] = True
            read_args["workflow_id"] = workflow_id

        flowcept_messages = Flowcept.read_buffer_file(**read_args)
        assert len(flowcept_messages) == 4


    @pytest.mark.safeoffline
    def test_data_files(self):
        with Flowcept() as f:
            used_args = {"a": 1}
            with FlowceptTask(used=used_args) as t:
                repo_root = Path(__file__).resolve().parents[2]
                img_path = repo_root / "docs" / "img" / "architecture-diagram.png"
                with open(img_path, "rb") as fp:
                    img_data = fp.read()

                t.end(generated={"b": 2}, data=img_data, custom_metadata={
                    "mime_type": "application/pdf", "file_name": "flowcept-logo.png", "file_extension": "pdf"}
                      )
                t.send()

            with FlowceptTask(used=used_args) as t:
                repo_root = Path(__file__).resolve().parents[2]
                img_path = repo_root / "docs" / "img" / "flowcept-logo.png"
                with open(img_path, "rb") as fp:
                    img_data = fp.read()

                t.end(generated={"c": 2}, data=img_data, custom_metadata={
                    "mime_type": "image/png", "file_name": "flowcept-logo.png", "file_extension": "png"}
                      )
                t.send()

            assert len(Flowcept.buffer) == 3
            assert Flowcept.buffer[1]["data"]
            #assert Flowcept.buffer[1]["data"].startswith(b"\x89PNG")


    @pytest.mark.safeoffline
    def test_prov_query_msg(self):
        with Flowcept():
            FlowceptTask(
                activity_id="hmi_message",
                subtype="agent_task",
                used={
                    "n": 1
                }
            ).send()
            sleep(1)
            FlowceptTask(
                activity_id="reset_user_context",
                subtype="call_agent_task",
                used={}
            ).send()
            sleep(1)
            FlowceptTask(
                activity_id="hmi_message",
                subtype="agent_task",
                used={
                    "n": 2
                }
            ).send()
            sleep(1)
            FlowceptTask(
                activity_id="hmi_message",
                subtype="agent_task",
                used={
                    "n": 3
                }
            ).send()


    @pytest.mark.safeoffline
    def test_prov_query_msg2(self):
        with Flowcept():
            FlowceptTask(
                activity_id="reset_user_context",
                subtype="call_agent_task",
                used={}
            ).send()
