import unittest

from uuid import uuid4

from dask.distributed import Client

from flowcept import FlowceptConsumerAPI, WorkflowObject, TaskQueryAPI

from flowcept.commons.flowcept_logger import FlowceptLogger

from flowcept.flowcept_api.db_api import DBAPI
from tests.adapters.dask_test_utils import (
    setup_local_dask_cluster,
    close_dask,
)
from tests.decorator_tests.ml_tests.dl_trainer import ModelTrainer


class MLDecoratorDaskTests(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MLDecoratorDaskTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    def test_model_trains_with_dask(self):
        wf_id = f"{uuid4()}"
        client, cluster, consumer = setup_local_dask_cluster(
            exec_bundle=wf_id
        )

        hp_conf = {
            "n_conv_layers": [2, 3, 4],
            "conv_incrs": [10, 20, 30],
            "n_fc_layers": [2, 4, 8],
            "fc_increments": [50, 100, 500],
            "softmax_dims": [1, 1, 1],
            "max_epochs": [1],
        }
        confs = ModelTrainer.generate_hp_confs(hp_conf)

        confs = [{**d, "workflow_id": wf_id} for d in confs]
        print("Workflow id", wf_id)
        outputs = []
        wf_obj = WorkflowObject()
        wf_obj.workflow_id = wf_id
        wf_obj.custom_metadata = {
            "hyperparameter_conf": hp_conf.update({"n_confs": len(confs)})
        }
        for conf in confs[:1]:
            conf["workflow_id"] = wf_id
            outputs.append(client.submit(ModelTrainer.model_fit, **conf))
        for o in outputs:
            r = o.result()
            print(r)
            assert "responsible_ai_metrics" in r

        close_dask(client, cluster)
        consumer.stop()

        from time import sleep

        sleep(30)
        # We are creating one "sub-workflow" for every Model.fit,
        # which requires forwarding on multiple layers
        task_query = TaskQueryAPI()
        module_docs = (
            task_query.get_subworkflows_tasks_from_a_parent_workflow(
                parent_workflow_id=wf_id
            )
        )
        assert len(module_docs) > 0
