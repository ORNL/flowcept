import unittest

import uuid

from dask.distributed import Client

from cluster_experiment_utils.utils import generate_configs

from flowcept import FlowceptConsumerAPI, WorkflowObject, DBAPI

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
        # Manually registering the DataPrep workflow (manual instrumentation)
        tokenizer = "toktok"  #  basic_english, moses, toktok
        db_api = DBAPI()
        dataset_prep_wf = WorkflowObject()
        dataset_prep_wf.workflow_id = f"prep_wikitext_tokenizer_{tokenizer}"
        dataset_prep_wf.used = {"tokenizer": tokenizer}
        ntokens, train_data, val_data, test_data = get_wiki_text(tokenizer)
        dataset_ref = f"{dataset_prep_wf.workflow_id}_{id(train_data)}_{id(val_data)}_{id(test_data)}"
        dataset_prep_wf.generated = {
            "ntokens": ntokens,
            "dataset_ref": dataset_ref,
            "train_data": id(train_data),
            "val_data": id(val_data),
            "test_data": id(test_data),
        }
        print(dataset_prep_wf)
        db_api.insert_or_update_workflow(dataset_prep_wf)

        # Automatically registering the Dask workflow
        train_wf_id = str(uuid.uuid4())
        client, cluster, consumer = setup_local_dask_cluster(
            exec_bundle=train_wf_id
        )
        register_dask_workflow(client,
                               workflow_id=train_wf_id,
                               used={"dataset_ref": dataset_ref})

        print(f"Model_Train_Wf_id={train_wf_id}")
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
                    "workflow_id": train_wf_id,
                }
            )
            outputs.append(client.submit(model_train, **conf))
        for o in outputs:
            o.result()

        close_dask(client, cluster)
        consumer.stop()
