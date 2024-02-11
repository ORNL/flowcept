import numpy as np

from flowcept import model_explainer

import unittest

from tests.decorator_tests.dl_trainer import ModelTrainer


class DecoratorTests(unittest.TestCase):
    # @staticmethod
    # def test_very_simple_decorator():
    #
    #     @model_explainer(background_size=3)
    #     def my_function(arg1):
    #         model = np.random.random()
    #         test_data = np.random.random(10) + arg1
    #         result = {
    #             "model": model,
    #             "test_data": test_data,
    #         }
    #         return result
    #
    #     result = my_function(10, 20)
    #     print(result)
    #     assert "shap_value" in result

    @staticmethod
    def test_model_trainer():
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
        for conf in confs:
            result = trainer.model_fit(**conf)
            print(result)
