import unittest
from uuid import uuid4
from flowcept.flowcept_api.db_api import DBAPI


class WorkflowDBTest(unittest.TestCase):

    def test_wf_dao(self):
        dbapi = DBAPI()
        assert dbapi.insert_or_update_workflow(workflow_id="wftest")

        assert dbapi.insert_or_update_workflow(
            workflow_id="wftest2",
            custom_metadata={"bla": "blu"},
            comment="comment test",
        )

        assert dbapi.insert_or_update_workflow(
            workflow_id="wftest2"
        )

        wfdata = dbapi.get_workflow(workflow_id="wftest2")
        assert wfdata is not None
        print(wfdata)

        wf3 = str(uuid4())

        assert dbapi.insert_or_update_workflow(workflow_id=wf3)
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf3, comment="test"
        )

        assert dbapi.get_workflow(workflow_id=wf3)
