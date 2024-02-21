import unittest

import uuid
from uuid import uuid4

from dask.distributed import Client

from cluster_experiment_utils.utils import generate_configs

from flowcept import FlowceptConsumerAPI, WorkflowObject

from flowcept.commons.flowcept_logger import FlowceptLogger

from flowcept.flowcept_api.db_api import DBAPI
from tests.decorator_tests.ml_tests.dl_trainer import ModelTrainer
from tests.adapters.test_dask import TestDask
from tests.decorator_tests.ml_tests.llm_trainer import (
    get_wiki_text,
    model_train,
)


class DecoratorDaskTests(unittest.TestCase):
    client: Client = None
    consumer: FlowceptConsumerAPI = None

    def __init__(self, *args, **kwargs):
        super(DecoratorDaskTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        TestDask.client = TestDask._setup_local_dask_cluster(n_workers=1)

    def test_model_trains(self):
        hp_conf = {
            "n_conv_layers": [2, 3, 4],
            "conv_incrs": [10, 20, 30],
            "n_fc_layers": [2, 4, 8],
            "fc_increments": [50, 100, 500],
            "softmax_dims": [1, 1, 1],
            "max_epochs": [1],
        }
        confs = ModelTrainer.generate_hp_confs(hp_conf)
        wf_id = f"wf_{uuid4()}"
        confs = [{**d, "workflow_id": wf_id} for d in confs]
        print(wf_id)
        outputs = []
        wf_obj = WorkflowObject()
        wf_obj.workflow_id = wf_id
        wf_obj.custom_metadata = {
            "hyperparameter_conf": hp_conf.update({"n_confs": len(confs)})
        }
        db = DBAPI()
        db.insert_or_update_workflow(wf_obj)
        for conf in confs[:1]:
            conf["workflow_id"] = wf_id
            outputs.append(
                TestDask.client.submit(ModelTrainer.model_fit, **conf)
            )
        for o in outputs:
            r = o.result()
            print(r)
            assert "responsible_ai_metrics" in r

        # db.dump_to_file(
        #     filter={"workflow_id": wf_id},
        #     output_file="tmp_sample_data_with_telemetry_and_rai.json",
        # )

    @staticmethod
    def test_model_trainer():
        trainer = ModelTrainer()
        result = trainer.model_fit(max_epochs=1)
        print(result)
        assert "shap_sum" in result["responsible_ai_metrics"]

    def test_llm(self):
        ntokens, train_data, val_data, test_data = get_wiki_text()

        # exp_param_settings = {
        #     "param_name1": {
        #         "init": 1,
        #         "end": 3,
        #         "step": 1,
        #     },
        #     "param_name2": {"init": [100, 200], "end": [500, 600],
        #                     "step": 100},
        #     "param_name4": {"init": 0.1, "end": 0.9, "step": 0.1},
        #     "param_name3": ["A", "B", "C"],
        #     "param_name5": [1e-1, 1e-2, 1e-3],
        # }

        wf_id = str(uuid.uuid4())
        print(f"Workflow_id={wf_id}")
        exp_param_settings = {
            "batch_size": [20],
            "eval_batch_size": [10],
            "emsize": [200],
            "nhid": [200],
            "nlayers": [2],  # 2
            "nhead": [2],
            "dropout": [0.2],
            "epochs": [1, 3],
            "lr": [0.1, 0.01],
            "pos_encoding_max_len": 5000,
        }
        configs = generate_configs(exp_param_settings)
        outputs = []
        for conf in configs:
            conf.update(
                {
                    "ntokens": ntokens,
                    "train_data": train_data,
                    "val_data": val_data,
                    "test_data": test_data,
                    "workflow_id": wf_id,
                }
            )
            outputs.append(TestDask.client.submit(model_train, **conf))
        for o in outputs:
            o.result()

    @classmethod
    def tearDownClass(cls):
        print("Closing scheduler and workers!")
        try:
            TestDask.client.shutdown()
        except:
            pass
        print("Closing flowcept!")
        if TestDask.consumer:
            TestDask.consumer.stop()
