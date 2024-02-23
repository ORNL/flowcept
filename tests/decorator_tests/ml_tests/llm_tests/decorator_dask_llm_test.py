import unittest

import uuid

from dask.distributed import Client

from cluster_experiment_utils.utils import generate_configs

from flowcept import FlowceptConsumerAPI

from flowcept.commons.flowcept_logger import FlowceptLogger
from tests.adapters.dask_test_utils import (
    setup_local_dask_cluster,
    close_dask,
)

from tests.adapters.test_dask import TestDask
from tests.decorator_tests.ml_tests.llm_tests.llm_trainer import (
    get_wiki_text,
    model_train,
)


class DecoratorDaskLLMTests(unittest.TestCase):
    client: Client = None
    cluster = None
    consumer: FlowceptConsumerAPI = None

    def __init__(self, *args, **kwargs):
        super(DecoratorDaskLLMTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        (
            DecoratorDaskLLMTests.client,
            DecoratorDaskLLMTests.cluster,
            DecoratorDaskLLMTests.consumer,
        ) = setup_local_dask_cluster(DecoratorDaskLLMTests.consumer)

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
        for conf in configs[:1]:
            conf.update(
                {
                    "ntokens": ntokens,
                    "train_data": train_data,
                    "val_data": val_data,
                    "test_data": test_data,
                    "workflow_id": wf_id,
                }
            )
            outputs.append(
                DecoratorDaskLLMTests.client.submit(model_train, **conf)
            )
        for o in outputs:
            o.result()

    @classmethod
    def tearDownClass(cls):
        print("Ending tests!")
        try:
            close_dask(
                DecoratorDaskLLMTests.client, DecoratorDaskLLMTests.cluster
            )
        except Exception as e:
            print(e)
            pass

        if TestDask.consumer:
            TestDask.consumer.stop()
