import unittest

from flowcept import (
    Flowcept,
    flowcept_task,
)
from flowcept.commons.utils import assert_by_querying_tasks_until


@flowcept_task
def sum_one(n):
    return n + 1


@flowcept_task
def mult_two(n):
    return n * 2


class FlowceptAPITest(unittest.TestCase):
    def test_simple_workflow(self):
        assert Flowcept.services_alive()

        with Flowcept(workflow_name="test_workflow"):
            n = 3
            o1 = sum_one(n)
            o2 = mult_two(o1)
            print(o2)

        assert assert_by_querying_tasks_until(
            {"workflow_id": Flowcept.current_workflow_id},
            condition_to_evaluate=lambda docs: len(docs) == 2,
        )

        print("workflow_id", Flowcept.current_workflow_id)

        assert (
            len(
                Flowcept.db.query(
                    filter={"workflow_id": Flowcept.current_workflow_id}
                )
            )
            == 2
        )
        assert (
            len(
                Flowcept.db.query(
                    type="workflow",
                    filter={"workflow_id": Flowcept.current_workflow_id},
                )
            )
            == 1
        )
