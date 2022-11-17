import unittest
from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor import (
    MLFlowInterceptor,
)

from flowcept.flowceptor.plugins.mlflow.mlflow_dataclasses import Run

# fmt: off
from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor_state_manager \
    import MLFlowInterceptorStateManager


class MLFlowDB(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MLFlowDB, self).__init__(*args, **kwargs)
        interceptor = MLFlowInterceptor()
        self.dao = interceptor.dao
        self.mlflow_state = MLFlowInterceptorStateManager(
            interceptor.plugin_key
        )
        self.mlflow_state.clear_set()

    def test_check_db(self):
        self.mlflow_state.add_element_id("f783309ac32f473b94fa48aa6d484306")
        self.mlflow_state.add_element_id("b885f7b3f05e4afe8f008a146fa09ec6")
        self.mlflow_state.add_element_id("22f19b78539b464fbc3a83f79c670e7f")

        runs = self.dao.get_runs()

        # Check if the last runs have been checked.
        for run_tuple in runs:
            run = Run(**run_tuple)
            if not self.mlflow_state.has_element_id(run.run_uuid):
                print("We need to intercept this! " + run.run_uuid)
                self.mlflow_state.add_element_id(run.run_uuid)

        print()


if __name__ == "__main__":
    unittest.main()
