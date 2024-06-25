import unittest

import uuid

from dask.distributed import Client

from cluster_experiment_utils.utils import generate_configs

from flowcept import FlowceptConsumerAPI

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.flowceptor.adapters.dask.dask_plugins import (
    register_dask_workflow,
)
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
    def __init__(self, *args, **kwargs):
        super(DecoratorDaskLLMTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    def test_llm(self):
        wf_id = str(uuid.uuid4())
        client, cluster, consumer = setup_local_dask_cluster(
            exec_bundle=wf_id
        )
        register_dask_workflow(client, workflow_id=wf_id)
        ntokens, train_data, val_data, test_data = get_wiki_text()
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
            outputs.append(client.submit(model_train, **conf))
        for o in outputs:
            o.result()

        close_dask(client, cluster)
        consumer.stop()
