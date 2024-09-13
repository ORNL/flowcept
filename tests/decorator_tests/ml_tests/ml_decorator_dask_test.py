import unittest

from flowcept import TaskQueryAPI

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import evaluate_until
from flowcept.flowceptor.adapters.dask.dask_plugins import (
    register_dask_workflow,
)

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
        # wf_id = f"{uuid4()}"
        client, cluster, consumer = setup_local_dask_cluster(
            # exec_bundle=wf_id
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
        hp_conf.update({"n_confs": len(confs)})
        custom_metadata = {"hyperparameter_conf": hp_conf}
        wf_id = register_dask_workflow(
            client, custom_metadata=custom_metadata
        )
        print("Workflow id", wf_id)
        for conf in confs:
            conf["workflow_id"] = wf_id

        outputs = []
        for conf in confs[:1]:
            outputs.append(client.submit(ModelTrainer.model_fit, **conf))
        for o in outputs:
            r = o.result()
            print(r)
            assert "responsible_ai_metadata" in r

        close_dask(client, cluster)
        consumer.stop()

        # We are creating one "sub-workflow" for every Model.fit,
        # which requires forwarding on multiple layers
        assert evaluate_until(
            lambda: len(
                TaskQueryAPI().get_subworkflows_tasks_from_a_parent_workflow(
                    wf_id
                )
            )
            > 0
        )
