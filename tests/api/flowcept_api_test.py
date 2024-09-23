import unittest
from time import sleep
from uuid import uuid4

from flowcept import (
    FlowceptConsumerAPI,
    WorkflowObject,
    DBAPI,
    INSTRUMENTATION,
    flowcept_task,
)
from flowcept.commons.utils import assert_by_querying_tasks_until


@flowcept_task
def sum_one(n, workflow_id=None):
    return n + 1


@flowcept_task
def mult_two(n, workflow_id=None):
    return n * 2


class FlowceptAPITest(unittest.TestCase):
    def test_simple_workflow(self):
        db = DBAPI()
        assert FlowceptConsumerAPI.services_alive()

        wf_id = str(uuid4())
        with FlowceptConsumerAPI(INSTRUMENTATION):
            # The next line is optional
            db.insert_or_update_workflow(WorkflowObject(workflow_id=wf_id))
            n = 3
            o1 = sum_one(n, workflow_id=wf_id)
            o2 = mult_two(o1, workflow_id=wf_id)
            print(o2)

        assert assert_by_querying_tasks_until(
            {"workflow_id": wf_id},
            condition_to_evaluate=lambda docs: len(docs) == 2,
        )

        print("workflow_id", wf_id)

        assert len(db.query(filter={"workflow_id": wf_id})) == 2
        assert (
            len(db.query(type="workflow", filter={"workflow_id": wf_id})) == 1
        )
