import uuid
from time import sleep
import pandas as pd

import flowcept.commons
import flowcept.instrumentation.decorators
from flowcept import FlowceptConsumerAPI

import unittest

from flowcept.instrumentation.decorators.flowcept_task import flowcept_task


@flowcept_task
def decorated_static_function(df: pd.DataFrame, workflow_id=None):
    return {"y": 2}


@flowcept_task
def decorated_static_function2(workflow_id=None):
    return [2]


@flowcept_task
def decorated_static_function3(x, workflow_id=None):
    return 3


class DecoratorTests(unittest.TestCase):
    @flowcept_task
    def decorated_function_with_self(self, x, workflow_id=None):
        sleep(x)
        return {"y": 2}

    def test_decorated_function(self):
        workflow_id = str(uuid.uuid4())
        # TODO :refactor-base-interceptor:
        with FlowceptConsumerAPI(
            interceptors=flowcept.instrumentation.decorators.instrumentation_interceptor
        ):
            self.decorated_function_with_self(x=0.1, workflow_id=workflow_id)
            decorated_static_function(pd.DataFrame(), workflow_id=workflow_id)
            decorated_static_function2(workflow_id)
            decorated_static_function3(0.1, workflow_id=workflow_id)
        print(workflow_id)
