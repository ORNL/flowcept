import unittest

from torch import nn

from flowcept import Flowcept
from flowcept.configs import MONGO_ENABLED
from tests.instrumentation_tests.ml_tests.dl_trainer import ModelTrainer, MyNet


class MLDecoratorTests(unittest.TestCase):
    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_torch_save_n_load(self):
        model = nn.Module()
        model_id = Flowcept.db.save_or_update_torch_model(model)
        new_model = nn.Module()
        doc = Flowcept.db.load_torch_model(model=new_model, object_id=model_id)
        print(doc)
        assert model.state_dict() == new_model.state_dict()

    @staticmethod
    def test_cnn_model_trainer():
        # Disable model mgmt if mongo not enabled
        if not MONGO_ENABLED:
            return

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
        with Flowcept():
            print("Parent workflow_id:" + Flowcept.current_workflow_id)
            for conf in confs[:1]:
                conf["workflow_id"] = Flowcept.current_workflow_id
                result = trainer.model_fit(**conf)
                assert len(result)

                c = conf.copy()
                c.pop("max_epochs")
                c.pop("workflow_id")
                loaded_model = MyNet(**c)

            model_doc = Flowcept.db.load_torch_model(loaded_model, result["best_obj_id"])
            print(model_doc)
            assert len(loaded_model(result["test_data"]))

