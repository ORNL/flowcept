import unittest
from uuid import uuid4

from flowcept import FlowceptConsumerAPI
from flowcept.commons.flowcept_dataclasses.workflow_object import (
    WorkflowObject,
)
from flowcept.commons.utils import assert_by_querying_tasks_until
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.instrumentation.decorators.flowcept_task import flowcept_task


@staticmethod
@flowcept_task
def sum_one(n, workflow_id=None):
    return n+1

@staticmethod
@flowcept_task
def mult_two(n, workflow_id=None):
    return n*2


class FlowceptAPITest(unittest.TestCase):

    def test_simple_workflow(self):
        wf_id = str(uuid4())
        with FlowceptConsumerAPI():
            # The next line is optional
            DBAPI().insert_or_update_workflow(WorkflowObject(workflow_id=wf_id))
            n = 3
            o1 = sum_one(n, workflow_id=wf_id)
            o2 = mult_two(o1, workflow_id=wf_id)
            print(o2)

        assert assert_by_querying_tasks_until(
            {"workflow_id": wf_id},
            condition_to_evaluate=lambda docs: len(docs) == 2,
        )
        print("workflow_id", wf_id)
