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
    client: Client = None
    cluster = None
    consumer: FlowceptConsumerAPI = None

    def __init__(self, *args, **kwargs):
        super(MLDecoratorDaskTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @classmethod
    def setUpClass(cls):
        (
            MLDecoratorDaskTests.client,
            MLDecoratorDaskTests.cluster,
            MLDecoratorDaskTests.consumer,
        ) = setup_local_dask_cluster(MLDecoratorDaskTests.consumer)

    def test_model_trains_with_dask(self):
        hp_conf = {
            "n_conv_layers": [2, 3, 4],
            "conv_incrs": [10, 20, 30],
            "n_fc_layers": [2, 4, 8],
            "fc_increments": [50, 100, 500],
            "softmax_dims": [1, 1, 1],
            "max_epochs": [1],
        }
        confs = ModelTrainer.generate_hp_confs(hp_conf)
        wf_id = f"{uuid4()}"
        confs = [{**d, "workflow_id": wf_id} for d in confs]
        print("Workflow id", wf_id)
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
                MLDecoratorDaskTests.client.submit(
                    ModelTrainer.model_fit, **conf
                )
            )
        for o in outputs:
            r = o.result()
            print(r)
            assert "responsible_ai_metrics" in r

        # We are creating one "sub-workflow" for every Model.fit,
        # which requires forwarding on multiple layers

        task_query = TaskQueryAPI()
        module_docs = task_query.get_subworkflow_tasks_from_a_parent_workflow(
            parent_workflow_id=wf_id
        )
        assert len(module_docs) > 0

        # db.dump_to_file(
        #     filter={"workflow_id": wf_id},
        #     output_file="tmp_sample_data_with_telemetry_and_rai.json",
        # )

    @classmethod
    def tearDownClass(cls):
        print("Ending tests!")
        try:
            close_dask(
                MLDecoratorDaskTests.client, MLDecoratorDaskTests.cluster
            )
        except Exception as e:
            print(e)
            pass

        if MLDecoratorDaskTests.consumer:
            MLDecoratorDaskTests.consumer.stop()
