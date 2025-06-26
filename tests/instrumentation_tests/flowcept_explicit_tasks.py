import unittest

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

