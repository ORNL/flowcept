import unittest
from uuid import uuid4
from flowcept.flowcept_api.db_api import DBAPI


class WorkflowDBTest(unittest.TestCase):
    def test_wf_dao(self):
        dbapi = DBAPI()
        wf1 = str(uuid4())

        assert dbapi.insert_or_update_workflow(
            workflow_id=wf1,
            custom_metadata={"bla": "blu"},
            comment="comment test",
        )

        assert dbapi.insert_or_update_workflow(
            workflow_id=wf1, custom_metadata={"bli": "blo"}
        )

        wfdata = dbapi.get_workflow(workflow_id=wf1)
        assert wfdata is not None
        print(wfdata)

        wf2 = str(uuid4())

        assert dbapi.insert_or_update_workflow(workflow_id=wf2)
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2, comment="test"
        )
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2, custom_metadata={"a": "b"}
        )
        assert dbapi.insert_or_update_workflow(
            workflow_id=wf2, custom_metadata={"c": "d"}
        )
        wfdata = dbapi.get_workflow(workflow_id=wf2)
        assert wfdata is not None
        assert len(wfdata["custom_metadata"]) == 2
