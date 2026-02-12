import unittest
import uuid

import pytest
from pathlib import Path
from time import sleep

from flowcept.commons.vocabulary import Status
from flowcept import Flowcept, FlowceptTask


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

    @pytest.mark.safeoffline
    def test_custom_tasks(self):

        flowcept = Flowcept(start_persistence=False, save_workflow=True, workflow_name="MyFirstWorkflow").start()

        agent1 = uuid.uuid4()
        t1 = FlowceptTask(activity_id="super_func1", used={"x":1}, agent_id=agent1, tags=["tag1"]).send()

        with FlowceptTask(activity_id="super_func2", used={"y": 1}, agent_id=agent1, tags=["tag2"]) as t2:
            sleep(0.5)
            t2.end(generated={"o": 3})

        t3 = FlowceptTask(activity_id="super_func3", used={"z": 1}, agent_id=agent1, tags=["tag3"])
        sleep(0.1)
        t3.end(generated={"w":1})

        flowcept.stop()

        flowcept_messages = Flowcept.read_buffer_file()
        for msg in flowcept_messages:
            print(msg)
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
