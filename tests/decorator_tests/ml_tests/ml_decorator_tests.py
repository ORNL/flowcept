import uuid
from time import sleep

import numpy as np
import torch
from torch import nn

import flowcept.commons
import flowcept.instrumentation.decorators
from flowcept import model_explainer, model_profiler, FlowceptConsumerAPI

import unittest

from flowcept.instrumentation.decorators.flowcept_task import flowcept_task
from tests.decorator_tests.ml_tests.dl_trainer import (
    ModelTrainer,
)
from tests.decorator_tests.ml_tests.llm_trainer import (
    model_train,
    get_wiki_text,
    TransformerModel,
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

    @staticmethod
    def test_llm_model_trainer():
        ntokens, train_data, val_data, test_data = get_wiki_text()
        wf_id = str(uuid.uuid4())
        # conf = {
        #      Original
        #     "batch_size": 20,
        #     "eval_batch_size": 10,
        #     "emsize": 200,
        #     "nhid": 200,
        #     "nlayers": 2, #2
        #     "nhead": 2,
        #     "dropout": 0.2,
        #     "epochs": 3,
        #     "lr": 0.001,
        #     "pos_encoding_max_len": 5000
        # }

        conf = {
            "batch_size": 20,
            "eval_batch_size": 10,
            "emsize": 200,
            "nhid": 200,
            "nlayers": 2,  # 2
            "nhead": 2,
            "dropout": 0.2,
            "epochs": 1,
            "lr": 0.1,
            "pos_encoding_max_len": 5000,
        }
        conf.update(
            {
                "ntokens": ntokens,
                "train_data": train_data,
                "val_data": val_data,
                "test_data": test_data,
                "workflow_id": wf_id,
            }
        )
        result = model_train(**conf)
        assert result
        print(MLDecoratorTests.debug_model_profiler(conf, ntokens, test_data))

    @staticmethod
    @model_profiler()
    def debug_model_profiler(conf, ntokens, test_data):
        best_m = TransformerModel(
            ntokens,
            conf["emsize"],
            conf["nhead"],
            conf["nhid"],
            conf["nlayers"],
            conf["dropout"],
        ).to("cpu")
        m = torch.load("transformer_wikitext2.pth")
        best_m.load_state_dict(m)
        return {
            "test_loss": 0.01,
            "train_loss": 0.01,
            "val_loss": 0.01,
            "model": best_m,
            "test_data": test_data,
        }
