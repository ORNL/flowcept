import unittest

import uuid

from dask.distributed import Client

from cluster_experiment_utils.utils import generate_configs

from flowcept import FlowceptConsumerAPI

from flowcept.commons.flowcept_logger import FlowceptLogger

from tests.adapters.test_dask import TestDask
from tests.decorator_tests.ml_tests.llm_tests.llm_trainer import (
    get_wiki_text,
    model_train,
)


class DecoratorDaskLLMTests(unittest.TestCase):
    client: Client = None
    consumer: FlowceptConsumerAPI = None

    def __init__(self, *args, **kwargs):
        super(DecoratorDaskLLMTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        TestDask.client = TestDask._setup_local_dask_cluster(n_workers=1)

    def test_llm(self):
        ntokens, train_data, val_data, test_data = get_wiki_text()

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
            "epochs": [1],
            "lr": [0.1],
            "pos_encoding_max_len": [5000],
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
