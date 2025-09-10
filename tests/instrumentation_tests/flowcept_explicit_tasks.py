import unittest
from pathlib import Path

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

    def test_data_files(self):
        with Flowcept() as f:
            used_args = {"a": 1}
            with FlowceptTask(used=used_args) as t:
                repo_root = Path(__file__).resolve().parents[2]
                img_path = repo_root / "docs" / "img" / "flowcept-logo.png"
                with open(img_path, "rb") as fp:
                    img_data = fp.read()

                t.end(generated={"b": 2}, data=img_data, custom_metadata={
                    "mime_type": "image/png", "file_name": "flowcept-logo.png", "file_extension": "png"}
                      )
                t.send()

            assert len(Flowcept.buffer) == 2
            assert Flowcept.buffer[1]["data"]
            assert Flowcept.buffer[1]["data"].startswith(b"\x89PNG")

