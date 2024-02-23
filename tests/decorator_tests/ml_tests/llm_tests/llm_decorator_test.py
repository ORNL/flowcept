import uuid

import torch

from flowcept import model_profiler

import unittest


from tests.decorator_tests.ml_tests.llm_tests.llm_trainer import (
    model_train,
    get_wiki_text,
    TransformerModel,
)


class LLMDecoratorTests(unittest.TestCase):
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
        print(
            LLMDecoratorTests.debug_model_profiler(conf, ntokens, test_data)
        )

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
