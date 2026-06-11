import unittest

import pytest

pytest.importorskip("torch")

from fastapi.testclient import TestClient

from flowcept import Flowcept

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import evaluate_until
from flowcept.configs import MONGO_ENABLED
from flowcept.webservice.main import create_app

from tests.adapters.dask_test_utils import (
    start_local_dask_cluster,
    stop_local_dask_cluster,
)
from tests.instrumentation_tests.ml_tests.dl_trainer import ModelTrainer


class MLDecoratorDaskTests(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MLDecoratorDaskTests, self).__init__(*args, **kwargs)
        self.logger = FlowceptLogger()

    @pytest.mark.safeoffline
    @unittest.skipIf(not MONGO_ENABLED, "MongoDB is disabled")
    def test_model_trains_with_dask(self):
        # wf_id = f"{uuid4()}"
        dask_client, cluster, flowcept = start_local_dask_cluster(
            n_workers=1,
            # exec_bundle=wf_id,
            start_persistence=True
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
        #custom_metadata = {"hyperparameter_conf": hp_conf}
        wf_id = Flowcept.current_workflow_id #save_dask_workflow(client, custom_metadata=custom_metadata)
        print("Workflow id", wf_id)
        for conf in confs:
            conf["workflow_id"] = wf_id

        outputs = []
        for conf in confs[:1]:
            outputs.append(dask_client.submit(ModelTrainer.model_fit, **conf))
        for o in outputs:
            r = o.result()
            print(r)

        stop_local_dask_cluster(dask_client, cluster, flowcept)

        ws_client = TestClient(create_app())

        def _has_subworkflow_tasks() -> bool:
            wf_resp = ws_client.get("/api/v1/workflows", params={"parent_workflow_id": wf_id, "limit": 1000})
            if wf_resp.status_code != 200:
                return False
            sub_wfs = wf_resp.json().get("items", [])
            if not sub_wfs:
                return False

            for sub_wf in sub_wfs:
                sub_wf_id = sub_wf.get("workflow_id")
                if not sub_wf_id:
                    continue
                task_resp = ws_client.get(f"/api/v1/tasks/by_workflow/{sub_wf_id}", params={"limit": 1000})
                if task_resp.status_code == 200 and task_resp.json().get("count", 0) > 0:
                    return True
            return False

        # We are creating one "sub-workflow" for every Model.fit,
        # which requires forwarding on multiple layers
        assert evaluate_until(_has_subworkflow_tasks)
