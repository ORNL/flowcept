"""Integration test for webservice routes backed by real Flowcept + MongoDB."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from flowcept import Flowcept, FlowceptTask
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.configs import MONGO_ENABLED
from flowcept.webservice.main import create_app


pytestmark = pytest.mark.skipif(not MONGO_ENABLED, reason="MongoDB is disabled")


def _wait_for(condition, timeout_sec: float = 20.0, interval_sec: float = 0.25) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(interval_sec)
    return False


def test_webservice_end_to_end_with_flowcept_and_blob_apis():
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    workflow_name = f"ws-workflow-{uuid4()}"

    workflow_id = None
    generic_obj_id = None
    dataset_obj_id = None
    model_obj_id = None

    with Flowcept(campaign_id=campaign_id, workflow_name=workflow_name):
        with FlowceptTask(activity_id="ws_task", used={"x": 1}) as task:
            task.end(generated={"y": 2})

        workflow_id = Flowcept.current_workflow_id

        generic_obj_id = Flowcept.db.save_or_update_object(
            object=b"generic-blob-payload",
            object_type="artifact",
            save_data_in_collection=True,
            custom_metadata={"kind": "generic"},
        )

        dataset_obj_id = Flowcept.db.save_or_update_dataset(
            object=b"dataset-blob-payload",
            save_data_in_collection=True,
            custom_metadata={"split": "train"},
        )

        model_obj_id = Flowcept.db.save_or_update_ml_model(
            object=b"model-blob-payload",
            save_data_in_collection=True,
            custom_metadata={"framework": "sklearn"},
        )

    assert workflow_id is not None
    assert generic_obj_id is not None
    assert dataset_obj_id is not None
    assert model_obj_id is not None

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 1)
    assert ok, "Timed out waiting for persisted tasks."

    task_doc = (Flowcept.db.task_query(filter={"workflow_id": workflow_id}, limit=1) or [None])[0]
    assert task_doc is not None
    task_id = task_doc["task_id"]

    app = create_app()
    client = TestClient(app)

    # Workflows: list/get/query including campaign_id filter support.
    rs = client.get("/api/v1/workflows", params={"campaign_id": campaign_id})
    assert rs.status_code == 200
    wf_items = rs.json()["items"]
    assert any(item["workflow_id"] == workflow_id for item in wf_items)

    rs = client.get(f"/api/v1/workflows/{workflow_id}")
    assert rs.status_code == 200
    assert rs.json()["campaign_id"] == campaign_id

    rs = client.post("/api/v1/workflows/query", json={"filter": {"campaign_id": campaign_id}, "limit": 10})
    assert rs.status_code == 200
    assert any(item["workflow_id"] == workflow_id for item in rs.json()["items"])

    # Tasks: list/get/query.
    rs = client.get("/api/v1/tasks", params={"workflow_id": workflow_id})
    assert rs.status_code == 200
    assert rs.json()["count"] >= 1

    rs = client.get(f"/api/v1/tasks/{task_id}")
    assert rs.status_code == 200
    assert rs.json()["workflow_id"] == workflow_id

    rs = client.post("/api/v1/tasks/query", json={"filter": {"workflow_id": workflow_id}, "limit": 10})
    assert rs.status_code == 200
    assert rs.json()["count"] >= 1

    # Objects: list/get/query/download.
    rs = client.get("/api/v1/objects", params={"workflow_id": workflow_id})
    assert rs.status_code == 200
    assert rs.json()["count"] >= 3

    rs = client.get(f"/api/v1/objects/{generic_obj_id}")
    assert rs.status_code == 200
    assert rs.json()["object_id"] == generic_obj_id

    rs = client.post("/api/v1/objects/query", json={"filter": {"workflow_id": workflow_id}, "limit": 20})
    assert rs.status_code == 200
    assert any(item["object_id"] == generic_obj_id for item in rs.json()["items"])

    rs = client.get(f"/api/v1/objects/{generic_obj_id}/download")
    assert rs.status_code == 200
    assert rs.content == b"generic-blob-payload"

    # Datasets: list/get/query/download.
    rs = client.get("/api/v1/datasets", params={"workflow_id": workflow_id})
    assert rs.status_code == 200
    assert any(item["object_id"] == dataset_obj_id for item in rs.json()["items"])

    rs = client.get(f"/api/v1/datasets/{dataset_obj_id}")
    assert rs.status_code == 200
    assert rs.json()["object_type"] == "dataset"

    rs = client.post("/api/v1/datasets/query", json={"filter": {"workflow_id": workflow_id}, "limit": 20})
    assert rs.status_code == 200
    assert any(item["object_id"] == dataset_obj_id for item in rs.json()["items"])

    rs = client.get(f"/api/v1/datasets/{dataset_obj_id}/download")
    assert rs.status_code == 200
    assert rs.content == b"dataset-blob-payload"

    # Models: list/get/query/download.
    rs = client.get("/api/v1/models", params={"workflow_id": workflow_id})
    assert rs.status_code == 200
    assert any(item["object_id"] == model_obj_id for item in rs.json()["items"])

    rs = client.get(f"/api/v1/models/{model_obj_id}")
    assert rs.status_code == 200
    assert rs.json()["object_type"] == "ml_model"

    rs = client.post("/api/v1/models/query", json={"filter": {"workflow_id": workflow_id}, "limit": 20})
    assert rs.status_code == 200
    assert any(item["object_id"] == model_obj_id for item in rs.json()["items"])

    rs = client.get(f"/api/v1/models/{model_obj_id}/download")
    assert rs.status_code == 200
    assert rs.content == b"model-blob-payload"

    # Cleanup singleton client handles for test isolation.
    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()
