import uuid

import unittest

from flowcept import TaskQueryAPI

from tests.decorator_tests.ml_tests.dl_trainer import (
    ModelTrainer,
)


class MLDecoratorTests(unittest.TestCase):
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
            print(result)

        task_query = TaskQueryAPI()
        module_docs = task_query.get_subworkflow_tasks_from_a_parent_workflow(
            parent_workflow_id=wf_id
        )
        assert len(module_docs) > 0
