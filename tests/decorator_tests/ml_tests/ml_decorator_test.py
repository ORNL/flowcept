import uuid

import unittest

from torch import nn

from flowcept import Flowcept
from tests.decorator_tests.ml_tests.dl_trainer import ModelTrainer, MyNet


class MLDecoratorTests(unittest.TestCase):

    def test_torch_save_n_load(self):
        model = nn.Module()
        model_id = Flowcept.db.save_torch_model(model)
        new_model = nn.Module()
        loaded_model = Flowcept.db.load_torch_model(model=new_model, object_id=model_id)
        assert model.state_dict() == loaded_model.state_dict()

    @staticmethod
    def test_cnn_model_trainer():
        trainer = ModelTrainer()

        hp_conf = {
            "n_conv_layers": [2, 3, 4],
            "conv_incrs": [10, 20, 30],
            "n_fc_layers": [2, 4, 8],
            "fc_increments": [50, 100, 500],
            "softmax_dims": [1, 1, 1],
            "max_epochs": [1],
        }
        confs = ModelTrainer.generate_hp_confs(hp_conf)
        wf_id = str(uuid.uuid4())
        print("Parent workflow_id:" + wf_id)
        for conf in confs[:1]:
            conf["workflow_id"] = wf_id
            result = trainer.model_fit(**conf)
            assert len(result)

            c = conf.copy()
            c.pop("max_epochs")
            c.pop("workflow_id")
            loaded_model = MyNet(**c)

            loaded_model = Flowcept.db.load_torch_model(
                loaded_model, result["object_id"]
            )
            assert len(loaded_model(result["test_data"]))


