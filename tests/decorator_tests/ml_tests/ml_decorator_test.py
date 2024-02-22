import uuid

import unittest
import numpy as np

import flowcept.commons
import flowcept.instrumentation.decorators
from flowcept import model_explainer, FlowceptConsumerAPI


from tests.decorator_tests.ml_tests.dl_trainer import (
    ModelTrainer,
)


class MLDecoratorTests(unittest.TestCase):
    @staticmethod
    def test_explainer_decorator():
        @model_explainer(background_size=3)
        def my_function(arg1):
            model = np.random.random()
            result = {
                "model": model,
            }
            return result

        result = my_function(10, 20)
        print(result)
        assert "shap_value" in result

    @staticmethod
    def test_cnn_model_trainer():
        trainer = ModelTrainer()

        hp_conf = {
            "n_conv_layers": [2, 3],  # ,4,5,6],
            "conv_incrs": [10, 20],  # ,30,40,50],
            "n_fc_layers": [2, 3],
            "fc_increments": [50, 100],
            "softmax_dims": [1, 1],
            "max_epochs": [1],
        }
        confs = ModelTrainer.generate_hp_confs(hp_conf)
        wf_id = str(uuid.uuid4())
        print("Parent workflow_id:" + wf_id)
        with FlowceptConsumerAPI(
            interceptors=flowcept.instrumentation.decorators.instrumentation_interceptor
        ):
            for conf in confs[:1]:
                conf["workflow_id"] = wf_id
                result = trainer.model_fit(**conf)
                print(result)
