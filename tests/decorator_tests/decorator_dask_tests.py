from uuid import uuid4

from dask.distributed import Client

from flowcept import FlowceptConsumerAPI
from flowcept.commons.flowcept_logger import FlowceptLogger

import unittest

from flowcept.flowcept_api.db_api import DBAPI
from tests.decorator_tests.dl_trainer import ModelTrainer
from tests.adapters.test_dask import TestDask


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
        db = DBAPI()
        db.insert_or_update_workflow(
            workflow_id=wf_id,
            custom_metadata=hp_conf.update({"n_confs": len(confs)}),
        )
        for conf in confs[:1]:
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
