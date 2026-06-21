"""Integration test for webservice routes backed by real Flowcept + MongoDB."""

from __future__ import annotations

import json
import re
import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from flowcept import Flowcept, FlowceptTask, WorkflowObject
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
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


def test_webservice_static_contract_routes():
    """Basic route contracts that do not need seeded provenance data."""
    from flowcept.version import __version__

    client = TestClient(create_app())

    rs = client.get("/api/v1/info")
    assert rs.status_code == 200
    assert rs.json() == {"service": "flowcept", "version": __version__}

    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"

    root = client.get("/")
    assert root.status_code == 200
    if root.headers["content-type"].startswith("application/json"):
        assert root.json()["service"] == "flowcept-webservice"
    else:
        assert "text/html" in root.headers["content-type"]

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    paths = openapi.json()["paths"]
    assert "/api/v1/workflows/{workflow_id}/workflow_card" in paths
    assert "/api/v1/workflows/{workflow_id}/provenance_card" not in paths
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


@pytest.fixture
def db_cleanup(request):
    """Track ids a test inserts and delete them from MongoDB/LMDB afterwards, even on failure.

    Tests register ids in the yielded dict; teardown recursively deletes campaigns
    (workflows + tasks + objects), then workflows, then standalone objects, and any
    agents registered during the test.
    """
    created = {"campaigns": [], "workflows": [], "objects": []}
    dao = DocumentDBDAO.get_instance(create_indices=False)

    initial_agents = set()
    if MONGO_ENABLED and hasattr(dao, "_agents_collection"):
        try:
            initial_agents = {a["agent_id"] for a in dao._agents_collection.find({}, {"agent_id": 1})}
        except Exception:
            pass

    from flowcept.configs import LMDB_ENABLED

    initial_lmdb_agents = set()
    if LMDB_ENABLED and hasattr(dao, "_agents_db"):
        try:
            with dao._env.begin(db=dao._agents_db) as txn:
                with txn.cursor() as cur:
                    for k, _ in cur:
                        initial_lmdb_agents.add(k)
        except Exception:
            pass

    yield created

    if request.config.getoption("--keep-webservice-test-data"):
        print(f"Keeping webservice test data for UI inspection: {created}")
        return

    # Re-retrieve active/fresh DAO because the old one might have been closed by Flowcept.stop()
    dao = DocumentDBDAO.get_instance(create_indices=False)

    for campaign_id in created["campaigns"]:
        dao.delete_campaign_data(campaign_id)
    for workflow_id in created["workflows"]:
        dao.delete_workflow_data(workflow_id)
    if created["objects"]:
        dao.delete_object_keys("object_id", created["objects"])

    # Clean up agents registered during this test
    if MONGO_ENABLED and hasattr(dao, "_agents_collection"):
        try:
            current_agents = {a["agent_id"] for a in dao._agents_collection.find({}, {"agent_id": 1})}
            new_agents = current_agents - initial_agents
            if new_agents:
                dao._agents_collection.delete_many({"agent_id": {"$in": list(new_agents)}})
        except Exception:
            pass

    if LMDB_ENABLED and hasattr(dao, "_agents_db"):
        try:
            current_lmdb_agents = set()
            with dao._env.begin(db=dao._agents_db) as txn:
                with txn.cursor() as cur:
                    for k, _ in cur:
                        current_lmdb_agents.add(k)
            new_lmdb_agents = current_lmdb_agents - initial_lmdb_agents
            if new_lmdb_agents:
                with dao._env.begin(write=True, db=dao._agents_db) as txn:
                    for k in new_lmdb_agents:
                        txn.delete(k)
        except Exception:
            pass

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


@pytest.fixture(scope="module")
def mcp_server_instance():
    """Run one MCP HTTP server per test process; reset context per test as needed."""
    from flowcept.agents.mcp import mcp_server as agent_module

    agent = agent_module.FlowceptMCPServer().start()
    try:
        yield agent
    finally:
        agent.stop()


def test_webservice_end_to_end_with_flowcept_and_blob_apis(db_cleanup):
    """End-to-end: real workflow + blob objects, then exercise the read APIs."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"GridSearchCampaign-{uuid4()}"
    workflow_name = f"ws-workflow-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)

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
    db_cleanup["objects"].extend([generic_obj_id, dataset_obj_id, model_obj_id])

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


def test_webservice_campaigns_agents_stats_and_prov_card(db_cleanup):
    """End-to-end test for derived campaigns/agents, stats endpoints, and workflow cards."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)
    workflow_name = f"ws-stats-workflow-{uuid4()}"
    agent_id = f"ws-agent-{uuid4()}"
    agent_name = "WSAgent"

    with Flowcept(
        campaign_id=campaign_id,
        workflow_name=workflow_name,
        agent_id=agent_id,
        agent_name=agent_name,
    ):
        workflow_id = Flowcept.current_workflow_id
        for i in range(3):
            with FlowceptTask(activity_id="preprocess", used={"i": i}) as task:
                task.end(generated={"out": i * 2})
        with FlowceptTask(activity_id="train", used={"epochs": 2}, agent_id=agent_id) as task:
            task.end(generated={"loss": 0.1})

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 4)
    assert ok, "Timed out waiting for persisted tasks."
    ok = _wait_for(lambda: Flowcept.db.get_workflow_object(workflow_id) is not None)
    assert ok, "Timed out waiting for persisted workflow."

    app = create_app()
    client = TestClient(app)

    # Campaigns: derived list and detail.
    rs = client.get("/api/v1/campaigns")
    assert rs.status_code == 200
    campaigns = {item["campaign_id"]: item for item in rs.json()["items"]}
    assert campaign_id in campaigns
    assert campaigns[campaign_id]["workflow_count"] >= 1
    assert campaigns[campaign_id]["task_count"] >= 4

    rs = client.get(f"/api/v1/campaigns/{campaign_id}")
    assert rs.status_code == 200
    body = rs.json()
    assert any(wf["workflow_id"] == workflow_id for wf in body["workflows"])
    assert body["task_summary"]["count"] >= 4

    rs = client.get(f"/api/v1/campaigns/non-existent-{uuid4()}")
    assert rs.status_code == 404

    # Agents: derived from task agent_id.
    rs = client.get("/api/v1/agents")
    assert rs.status_code == 200
    assert any(item["agent_id"] == agent_id for item in rs.json()["items"])

    rs = client.get(f"/api/v1/agents/{agent_id}")
    assert rs.status_code == 200
    assert rs.json()["agent"]["task_count"] == 1
    assert "train" in rs.json()["agent"]["activities"]

    rs = client.get(f"/api/v1/agents/{agent_id}/tasks")
    assert rs.status_code == 200
    assert rs.json()["count"] == 1

    # Stats: task summary, timeseries, and card-data resolver.
    rs = client.get("/api/v1/stats/tasks/summary", params={"workflow_id": workflow_id})
    assert rs.status_code == 200
    summary = rs.json()
    assert summary["count"] >= 4
    activities = {a["activity_id"]: a for a in summary["activity_stats"]}
    assert activities["preprocess"]["count"] == 3
    assert activities["train"]["count"] == 1
    assert summary["time_range"]["min_started_at"] is not None

    rs = client.post(
        "/api/v1/stats/timeseries",
        json={"filter": {"workflow_id": workflow_id}, "fields": ["ended_at"], "x": "started_at"},
    )
    assert rs.status_code == 200
    assert rs.json()["count"] >= 4
    assert all(row["started_at"] is not None for row in rs.json()["rows"])

    rs = client.post(
        "/api/v1/stats/chart_data",
        json={
            "data": {
                "source": "tasks",
                "group_by": "activity_id",
                "metrics": [{"field": "", "agg": "count"}],
            },
            "context": {"workflow_id": workflow_id},
        },
    )
    assert rs.status_code == 200
    rows = {row["activity_id"]: row for row in rs.json()["rows"]}
    assert rows["preprocess"]["count"] == 3
    assert rows["train"]["count"] == 1

    # Rejected operator must 400.
    rs = client.get("/api/v1/stats/tasks/summary", params={"filter_json": '{"$where": "1"}'})
    assert rs.status_code == 400

    # Workflow card: JSON and markdown content.
    rs = client.get(f"/api/v1/workflows/{workflow_id}/workflow_card", params={"format": "json"})
    assert rs.status_code == 200
    card = rs.json()
    assert card["input_mode"] == "db"
    assert "transformations" in card and "dataset" in card

    rs = client.get(f"/api/v1/workflows/{workflow_id}/workflow_card", params={"format": "markdown"})
    assert rs.status_code == 200
    assert rs.headers["content-type"].startswith("text/markdown")
    assert workflow_name in rs.text or workflow_id in rs.text

    rs = client.get(f"/api/v1/campaigns/{campaign_id}/workflow_card", params={"format": "markdown"})
    assert rs.status_code == 200

    rs = client.get(f"/api/v1/workflows/{workflow_id}/workflow_card", params={"format": "pdf"})
    assert rs.status_code == 200
    assert rs.headers["content-type"].startswith("application/pdf")
    assert rs.headers["content-disposition"] == f'attachment; filename="workflow_card_{workflow_id}.pdf"'

    rs = client.get(f"/api/v1/workflows/non-existent-{uuid4()}/workflow_card", params={"format": "markdown"})
    assert rs.status_code == 404

    # Cleanup singleton client handles for test isolation.
    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_webservice_object_versioning_and_unified_query(db_cleanup):
    """End-to-end test for object version history and the unified /query/{scope} endpoint."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    obj_id = f"ws-versioned-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)
    db_cleanup["objects"].append(obj_id)

    with Flowcept(campaign_id=campaign_id, workflow_name=f"ws-version-wf-{uuid4()}"):
        workflow_id = Flowcept.current_workflow_id
        with FlowceptTask(activity_id="emit", used={"x": 1}) as task:
            task.end(generated={"y": 1})
        for version in range(2):
            Flowcept.db.save_or_update_object(
                object=f"payload-v{version}".encode(),
                object_id=obj_id,
                object_type="ml_model",
                save_data_in_collection=True,
                custom_metadata={"v": version},
                control_version=True,
            )

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 1)
    assert ok, "Timed out waiting for persisted tasks."

    app = create_app()
    client = TestClient(app)

    # Version history and per-version metadata/downloads.
    rs = client.get(f"/api/v1/objects/{obj_id}/history")
    assert rs.status_code == 200
    versions = sorted(item["version"] for item in rs.json()["items"])
    assert versions == [0, 1]

    rs = client.get(f"/api/v1/objects/{obj_id}/versions/0")
    assert rs.status_code == 200
    assert rs.json()["custom_metadata"]["v"] == 0

    rs = client.get(f"/api/v1/objects/{obj_id}/versions/0/download")
    assert rs.status_code == 200
    assert rs.content == b"payload-v0"

    rs = client.get(f"/api/v1/objects/{obj_id}/download")
    assert rs.status_code == 200
    assert rs.content == b"payload-v1"

    # Models scope sees the versioned object; include_data exposes payload.
    rs = client.get(f"/api/v1/models/{obj_id}", params={"include_data": "true"})
    assert rs.status_code == 200
    assert rs.json()["object_type"] == "ml_model"
    assert rs.json().get("data")

    # Unified scoped query: operators, sort, projection, limit.
    rs = client.post(
        "/api/v1/query/tasks",
        json={
            "filter": {"workflow_id": workflow_id, "started_at": {"$exists": True}},
            "projection": ["task_id", "activity_id", "started_at"],
            "sort": [{"field": "started_at", "order": -1}],
            "limit": 5,
        },
    )
    assert rs.status_code == 200
    assert rs.json()["count"] >= 1
    assert all("used" not in item for item in rs.json()["items"])

    rs = client.post("/api/v1/query/models", json={"filter": {"object_id": obj_id}, "limit": 5})
    assert rs.status_code == 200
    assert all(item["object_type"] == "ml_model" for item in rs.json()["items"])

    # Disallowed operator is rejected.
    rs = client.post("/api/v1/query/tasks", json={"filter": {"$where": "1"}, "limit": 5})
    assert rs.status_code == 400

    # Tasks by workflow + filter_json list filters.
    rs = client.get(f"/api/v1/tasks/by_workflow/{workflow_id}")
    assert rs.status_code == 200
    assert rs.json()["count"] >= 1

    rs = client.get("/api/v1/tasks", params={"filter_json": f'{{"workflow_id": "{workflow_id}"}}'})
    assert rs.status_code == 200
    assert rs.json()["count"] >= 1

    rs = client.get("/api/v1/tasks/")
    assert rs.status_code == 404

    rs = client.get("/api/v1/tasks", params={"filter_json": "[]"})
    assert rs.status_code == 400

    rs = client.post(
        "/api/v1/tasks/query",
        json={
            "filter": {},
            "projection": ["task_id", "workflow_id"],
            "aggregation": [{"operator": "max", "field": "started_at"}],
            "limit": 10,
        },
    )
    assert rs.status_code == 400

    rs = client.post(f"/api/v1/workflows/{workflow_id}/reports/workflow-card/download")
    assert rs.status_code == 200
    assert rs.headers["content-type"].startswith("text/markdown")
    assert rs.headers["content-disposition"] == f'attachment; filename="workflow_card_{workflow_id}.md"'

    rs = client.get(f"/api/v1/workflows/non-existent-{uuid4()}")
    assert rs.status_code == 404

    rs = client.get("/api/v1/workflows", params={"filter_json": "not-json"})
    assert rs.status_code == 400

    rs = client.post(f"/api/v1/workflows/non-existent-{uuid4()}/reports/workflow-card/download")
    assert rs.status_code == 404

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_webservice_dashboards_crud():
    """End-to-end CRUD test for dashboards stored in the real backend."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    app = create_app()
    client = TestClient(app)

    target = f"wf-name-{uuid4()}"
    config = {
        "dashboard_type": "custom_workflow",
        "target": target,
        "name": f"dash-{uuid4()}",
        "charts": [
            {
                "chart_id": "c1",
                "type": "chart",
                "title": "Tasks per activity",
                "data": {
                    "source": "tasks",
                    "group_by": "activity_id",
                    "metrics": [{"field": "", "agg": "count"}],
                },
                "viz": {"kind": "bar"},
            },
            {"chart_id": "c2", "type": "markdown", "content": "# Notes"},
        ],
    }

    rs = client.post("/api/v1/dashboards", json=config)
    assert rs.status_code == 201, rs.text
    created = rs.json()
    dashboard_id = created["dashboard_id"]
    assert dashboard_id and created["created_at"]

    try:
        rs = client.get(f"/api/v1/dashboards/{dashboard_id}")
        assert rs.status_code == 200
        assert rs.json()["name"] == config["name"]
        assert len(rs.json()["charts"]) == 2

        rs = client.get("/api/v1/dashboards")
        assert rs.status_code == 200
        assert any(d["dashboard_id"] == dashboard_id for d in rs.json()["items"])

        rs = client.get("/api/v1/dashboards", params={"dashboard_type": "custom_workflow"})
        assert rs.status_code == 200
        assert any(d["dashboard_id"] == dashboard_id for d in rs.json()["items"])

        # Resolution merges common_workflow charts with this workflow's custom charts.
        rs = client.get("/api/v1/dashboards/resolve", params={"workflow_name": target})
        assert rs.status_code == 200
        resolved_ids = {c["chart_id"] for c in rs.json()}
        assert {"c1", "c2"}.issubset(resolved_ids)

        rs = client.get("/api/v1/dashboards/resolve")
        assert rs.status_code == 400

        updated = dict(config, name="updated")
        rs = client.put(f"/api/v1/dashboards/{dashboard_id}", json=updated)
        assert rs.status_code == 200
        assert rs.json()["name"] == "updated"
        assert rs.json()["created_at"] == created["created_at"]
        assert rs.json()["updated_at"] >= created["updated_at"]

        # Validation: bad chart type, bad dashboard type, and disallowed filter operator.
        bad = dict(config, charts=[{"chart_id": "x", "type": "nope"}])
        rs = client.post("/api/v1/dashboards", json=bad)
        assert rs.status_code == 422

        bad = dict(config, dashboard_type="nope")
        rs = client.post("/api/v1/dashboards", json=bad)
        assert rs.status_code == 422

        bad_chart = dict(config["charts"][0])
        bad_chart["data"] = dict(bad_chart["data"], filter={"$where": "1"})
        bad = dict(config, charts=[bad_chart])
        rs = client.post("/api/v1/dashboards", json=bad)
        assert rs.status_code == 400
    finally:
        rs = client.delete(f"/api/v1/dashboards/{dashboard_id}")
        assert rs.status_code == 200

    rs = client.get(f"/api/v1/dashboards/{dashboard_id}")
    assert rs.status_code == 404

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def _start_real_server(app):
    """Run the app on a real uvicorn server in a thread; return (server, thread, base_url)."""
    import socket

    import uvicorn
    from sse_starlette.sse import AppStatus

    # sse-starlette's exit Event binds to the first serving loop; reset per server (see
    # FlowceptAgent._run_server for the same workaround).
    AppStatus.should_exit_event = None

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    assert _wait_for(lambda: server.started, timeout_sec=15), "Webservice did not start."
    return server, thread, f"http://127.0.0.1:{port}"


def _stop_real_server(server, thread):
    server.should_exit = True
    thread.join(timeout=10)


def _read_sse_events(line_iter, max_events: int, timeout_sec: float = 15.0):
    """Collect up to ``max_events`` parsed SSE events from an iterator of lines."""
    events = []
    current_event, current_data = None, []
    deadline = time.time() + timeout_sec
    for line in line_iter:
        if time.time() > deadline:
            break
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            current_data.append(line.split(":", 1)[1].strip())
        elif line == "" and current_event:
            events.append((current_event, json.loads("".join(current_data) or "null")))
            current_event, current_data = None, []
            if len(events) >= max_events:
                break
    return events


def test_webservice_stream_tasks_sse(db_cleanup):
    """End-to-end SSE: existing tasks arrive in the first event; mid-stream inserts arrive next."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)

    with Flowcept(campaign_id=campaign_id, workflow_name=f"ws-sse-wf-{uuid4()}"):
        workflow_id = Flowcept.current_workflow_id
        with FlowceptTask(activity_id="sse_seed", used={"i": 0}) as task:
            task.end(generated={"o": 0})

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 1)
    assert ok, "Timed out waiting for persisted tasks."

    import httpx

    server, server_thread, base_url = _start_real_server(create_app())

    late_task_id = f"sse-late-{uuid4()}"

    def _insert_late_task():
        time.sleep(0.8)
        now = time.time()
        task = TaskObject()
        task.task_id = late_task_id
        task.workflow_id = workflow_id
        task.activity_id = "sse_late"
        task.started_at = now
        task.ended_at = now
        task.registered_at = now
        Flowcept.db.insert_or_update_task(task)

    inserter = threading.Thread(target=_insert_late_task, daemon=True)

    try:
        with httpx.stream(
            "GET",
            f"{base_url}/api/v1/stream/tasks?workflow_id={workflow_id}&since=0&poll_interval=0.2",
            timeout=httpx.Timeout(20.0),
        ) as rs:
            assert rs.status_code == 200
            assert rs.headers["content-type"].startswith("text/event-stream")
            inserter.start()
            events = _read_sse_events(rs.iter_lines(), max_events=2)
    finally:
        _stop_real_server(server, server_thread)

    assert len(events) == 2
    name0, payload0 = events[0]
    assert name0 == "tasks"
    assert any(t["activity_id"] == "sse_seed" for t in payload0["tasks"])
    assert payload0["cursor"] > 0

    name1, payload1 = events[1]
    assert name1 == "tasks"
    assert any(t["task_id"] == late_task_id for t in payload1["tasks"])
    assert payload1["cursor"] >= payload0["cursor"]

    inserter.join(timeout=5)

    # Cursor semantics: since=<latest cursor> + a fresh insert returns only the new task.
    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_webservice_stream_workflows_sse(db_cleanup):
    """End-to-end SSE for the workflows stream filtered by campaign."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)
    with Flowcept(campaign_id=campaign_id, workflow_name=f"ws-sse-wf2-{uuid4()}"):
        workflow_id = Flowcept.current_workflow_id

    ok = _wait_for(lambda: len(Flowcept.db.workflow_query(filter={"workflow_id": workflow_id}) or []) >= 1)
    assert ok, "Timed out waiting for persisted workflow."

    import httpx

    server, server_thread, base_url = _start_real_server(create_app())
    try:
        with httpx.stream(
            "GET",
            f"{base_url}/api/v1/stream/workflows?campaign_id={campaign_id}&since=0&poll_interval=0.2",
            timeout=httpx.Timeout(20.0),
        ) as rs:
            assert rs.status_code == 200
            events = _read_sse_events(rs.iter_lines(), max_events=1)
    finally:
        _stop_real_server(server, server_thread)

    assert len(events) == 1
    name, payload = events[0]
    assert name == "workflows"
    assert any(w["workflow_id"] == workflow_id for w in payload["workflows"])

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_webservice_spa_serving(tmp_path, monkeypatch):
    """SPA assets are served at root with index.html fallback when present."""
    from flowcept.webservice import main as ws_main

    # Without assets: root returns the API status payload.
    missing_dir = tmp_path / "no_ui"
    monkeypatch.setattr(ws_main, "Path", lambda *_: missing_dir / "main.py")
    client = TestClient(ws_main.create_app())
    rs = client.get("/")
    assert rs.status_code == 200
    assert rs.json()["service"] == "flowcept-webservice"

    # With real assets on disk: index.html served at root and for SPA routes; API still wins.
    ui_dir = tmp_path / "ui_build"
    (ui_dir / "assets").mkdir(parents=True)
    (ui_dir / "index.html").write_text("<html><body>flowcept-ui</body></html>")
    (ui_dir / "assets" / "app.js").write_text("console.log('ui')")

    monkeypatch.setattr(ws_main, "Path", lambda *_: tmp_path / "main.py")
    client = TestClient(ws_main.create_app())

    rs = client.get("/")
    assert rs.status_code == 200
    assert "flowcept-ui" in rs.text

    rs = client.get("/workflows/some-id")
    assert "flowcept-ui" in rs.text

    rs = client.get("/assets/app.js")
    assert rs.status_code == 200
    assert "console.log" in rs.text

    rs = client.get("/api/v1/health/live")
    assert rs.status_code == 200
    assert rs.json() != {}

    rs = client.get("/api/v1/this/does/not/exist")
    assert rs.status_code == 404


def test_prov_tools_shared_core(db_cleanup):
    """The shared provenance tool core (used by web chat and MCP agent) works on real data."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    from flowcept.agents.data_query_tools.db_query_tools import (
        get_task_summary,
        list_campaigns,
        query_tasks,
        query_workflows,
    )
    from flowcept.agents.data_query_tools.dashboard_tools import (
        make_chart,
        get_dashboard,
    )

    campaign_id = f"ws-campaign-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)
    with Flowcept(campaign_id=campaign_id, workflow_name=f"ws-tools-wf-{uuid4()}"):
        workflow_id = Flowcept.current_workflow_id
        with FlowceptTask(activity_id="tool_seed", used={"x": 1}) as task:
            task.end(generated={"y": 2})

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 1)
    assert ok, "Timed out waiting for persisted tasks."

    result = query_tasks(filter={"workflow_id": workflow_id}, limit=10)
    assert result.code in (201, 301)
    assert any(t["activity_id"] == "tool_seed" for t in result.result["items"])

    result = query_workflows(filter={"campaign_id": campaign_id})
    assert result.code in (201, 301)
    assert any(w["workflow_id"] == workflow_id for w in result.result["items"])

    result = get_task_summary(filter={"workflow_id": workflow_id})
    assert result.result["count"] >= 1

    result = list_campaigns()
    assert any(c["campaign_id"] == campaign_id for c in result.result["items"])

    result = make_chart(
        card_spec={
            "chart_id": "chat-c1",
            "type": "chart",
            "title": "tasks per activity",
            "data": {"source": "tasks", "filter": {"workflow_id": workflow_id}, "group_by": "activity_id"},
            "viz": {"kind": "bar"},
        }
    )
    assert result.code in (201, 301)
    assert result.result["rows"]
    assert result.result["chart"]["chart_id"] == "chat-c1"

    # get_dashboard returns 404 for unknown id (no real dashboard needed).
    result = get_dashboard("nonexistent-dashboard-id")
    assert result.code == 404

    # Disallowed filter operators are rejected by the shared core.
    result = query_tasks(filter={"$where": "1"}, limit=10)
    assert result.code >= 400

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_chat_endpoint_unavailable_without_llm():
    """POST /api/v1/chat returns 503 with a clear detail when no LLM is configured."""
    from flowcept.configs import AGENT

    api_key = AGENT.get("api_key")
    if api_key and api_key != "?":
        pytest.skip("An LLM is configured; the 503 path does not apply.")

    app = create_app()
    client = TestClient(app)
    rs = client.post("/api/v1/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert rs.status_code == 503
    assert "LLM" in rs.json()["detail"] or "llm" in rs.json()["detail"]


def _load_chat_query_cases():
    """Load path-agnostic chat integration questions."""
    import pathlib
    import yaml

    yaml_path = pathlib.Path(__file__).parent / "chat_query_tests.yaml"
    cases = yaml.safe_load(yaml_path.read_text())
    assert cases, "No chat query cases found in chat_query_tests.yaml"
    return cases


def _chat_response_score(actual: str, expected: str) -> float:
    """Return a simple token-overlap score for path-agnostic chat answer checks."""
    import re

    def _tokens(text: str) -> set[str]:
        tokens = set()
        for raw_token in re.findall(r"[a-zA-Z0-9_.]+", text.lower()):
            token = raw_token.strip(".")
            tokens.add(token)
            tokens.update(part for part in token.split(".") if part)
        return {token for token in tokens if token}

    actual_tokens = _tokens(actual)
    expected_tokens = _tokens(expected)
    if not expected_tokens:
        return 1.0
    return len(actual_tokens & expected_tokens) / len(expected_tokens)


def _load_gridsearch_context_into_mcp(gridsearch_run_data, mcp_server_instance):
    """Load workflow + task messages into MCP context for schema and runtime-memory paths."""
    from flowcept.agents.mcp.mcp_client import run_tool
    from flowcept.commons.utils import sanitize_json_like

    tasks = gridsearch_run_data["tasks"] or []
    assert tasks, "gridsearch_run_data contains no tasks."
    workflow_obj = Flowcept.db.get_workflow_object(gridsearch_run_data["workflow_id"])
    assert workflow_obj is not None
    messages = sanitize_json_like([workflow_obj.to_dict(), *tasks], mongo_safe_keys=True)
    loaded_result = run_tool("load_buffer_messages", kwargs={"messages": messages})[0]
    assert '"code": 201' in loaded_result
    loaded = run_tool(
        "run_df_query",
        kwargs={"query": "result = len(df)", "plot": False, "context_kind": "tasks"},
    )[0]
    assert "Current df is empty or null" not in loaded


@pytest.mark.llm
@pytest.mark.parametrize(
    ("tool_context", "expected_tool_names"),
    [
        (
            "db",
            {
                "query_tasks",
                "query_workflows",
                "get_task_summary",
                "list_campaigns",
                "list_agents",
                "highlight_lineage",
                "make_chart",
            },
        ),
        (
            "df",
            {
                "generate_result_df",
                "generate_plot_code",
                "extract_or_fix_python_code",
                "get_workflow_context",
                "run_df_query",
                "list_agents",
            },
        ),
    ],
)
def test_chat_endpoint_real_llm_queries(gridsearch_run_data, mcp_server_instance, tool_context, expected_tool_names):
    """Every YAML chat question works through HTTP -> LangGraph -> MCP for both tool contexts."""
    from flowcept.configs import AGENT

    api_key = AGENT.get("api_key")
    if not api_key or api_key in ("?", "your-api-key-here"):
        pytest.skip("agent.api_key is not set.")
    if not AGENT.get("service_provider") or AGENT.get("service_provider") == "?":
        pytest.skip("agent.service_provider is not set.")

    campaign_id = gridsearch_run_data["campaign_id"]
    workflow_id = gridsearch_run_data["workflow_id"]

    app = create_app()
    client = TestClient(app)
    _load_gridsearch_context_into_mcp(gridsearch_run_data, mcp_server_instance)

    import os

    case_id_filter = {c.strip() for c in os.environ.get("CHAT_TEST_CASE_IDS", "").split(",") if c.strip()}

    for case in _load_chat_query_cases():
        # Skip cases restricted to a different tool_context.
        allowed_contexts = case.get("tool_contexts", ["db", "df"])
        if tool_context not in allowed_contexts:
            continue
        # Skip cases not in the explicit case_id filter (when set).
        case_id = case.get("case_id")
        if case_id_filter and case_id not in case_id_filter:
            continue

        rs = client.post(
            "/api/v1/chat",
            json={
                "messages": [{"role": "user", "content": case["user_query"]}],
                "context": {"campaign_id": campaign_id, "workflow_id": workflow_id, "tool_context": tool_context},
                "stream": False,
            },
        )
        assert rs.status_code == 200, f"HTTP error for query: {case['user_query']!r}; body={rs.text}"
        body = rs.json()
        actual = body.get("message", "")
        tool_trace = body.get("tool_trace") or []
        assert actual, f"Empty response for query: {case['user_query']!r}"
        assert tool_trace, f"LLM made no tool call for query: {case['user_query']!r}"
        score = _chat_response_score(actual, case["expected_response"])
        assert score >= case["score_threshold"], (
            f"Low answer score for {tool_context} query {case['user_query']!r}: "
            f"score={score:.2f}, threshold={case['score_threshold']:.2f}\n"
            f"Expected: {case['expected_response']}\nActual: {actual}"
        )
        assert any(
            event.get("name") in expected_tool_names or event.get("tool_name") in expected_tool_names
            for event in tool_trace
        ), f"Expected MCP {tool_context} tool path for query {case['user_query']!r}; trace={tool_trace!r}"

        # Optional structured-response assertions.
        tool_expected = case.get("tool_expected")
        if tool_expected == "make_chart":
            cards = body.get("cards") or []
            assert cards, f"Expected card event for make_chart in query {case['user_query']!r}"
        elif tool_expected == "generate_plot_code":
            assert any(
                e.get("name") == "generate_plot_code" for e in tool_trace
            ), f"Expected generate_plot_code in tool_trace for query {case['user_query']!r}; trace={tool_trace!r}"

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


@pytest.mark.llm
def test_chat_endpoint_records_ai_model_usage_tasks(gridsearch_run_data, db_cleanup, mcp_server_instance):
    """A chat request creates a Flowcept workflow with AI model invocation provenance."""
    from flowcept.agents.chat_orchestration.chat_orchestrator_service import CHAT_WORKFLOW_NAME
    from flowcept.commons.vocabulary import PROV_AGENT

    services = Flowcept.services_alive()
    if not services:
        pytest.skip(f"Flowcept services are not alive: {services}")
    if services.get("llm") != "ok":
        pytest.skip(f"LLM provider is not configured or not alive: {services}")

    workflow_id = gridsearch_run_data["workflow_id"]
    before = {wf["workflow_id"] for wf in Flowcept.db.workflow_query(filter={"name": CHAT_WORKFLOW_NAME}) or []}

    client = TestClient(create_app())
    mcp_server_instance.reset_context()
    rs = client.post(
        "/api/v1/chat",
        json={
            "messages": [{"role": "user", "content": "How many tasks are in this workflow? Use the query_tasks tool."}],
            "context": {"workflow_id": workflow_id},
            "stream": False,
        },
    )

    assert rs.status_code == 200, rs.text
    assert rs.json().get("message")
    assert rs.json().get("tool_trace")

    def _new_chat_workflow_ids():
        workflows = Flowcept.db.workflow_query(filter={"name": CHAT_WORKFLOW_NAME}) or []
        return [wf["workflow_id"] for wf in workflows if wf["workflow_id"] not in before]

    ok = _wait_for(lambda: len(_new_chat_workflow_ids()) >= 1)
    assert ok, "Timed out waiting for chat workflow to be persisted."
    chat_workflow_id = _new_chat_workflow_ids()[0]
    db_cleanup["workflows"].append(chat_workflow_id)

    ok = _wait_for(
        lambda: len(
            Flowcept.db.task_query(
                filter={
                    "workflow_id": chat_workflow_id,
                    "subtype": PROV_AGENT.AI_MODEL_INVOCATION.value,
                }
            )
            or []
        )
        >= 1
    )
    assert ok, "Timed out waiting for AI model invocation task to be persisted."

    llm_tasks = (
        Flowcept.db.task_query(
            filter={"workflow_id": chat_workflow_id, "subtype": PROV_AGENT.AI_MODEL_INVOCATION.value},
        )
        or []
    )
    llm_task = llm_tasks[0]
    assert llm_task["subtype"] == PROV_AGENT.AI_MODEL_INVOCATION.value
    assert "telemetry_at_start" not in llm_task
    assert "telemetry_at_end" not in llm_task
    usage = llm_task["custom_metadata"]["llm_usage"]
    assert usage["model"]
    assert usage["input_chars"] > 0
    assert usage["output_tokens"] is None or usage["output_tokens"] > 0
    assert "provider_response_metadata" in usage
    assert any(task["custom_metadata"]["llm_usage"]["output_chars"] > 0 for task in llm_tasks)

    tool_tasks = Flowcept.db.task_query(
        filter={"workflow_id": chat_workflow_id, "subtype": PROV_AGENT.AGENT_TOOL.value},
    )
    assert tool_tasks, "The forced DB query should record at least one agent tool task."


def test_recursive_delete_workflow_and_campaign(db_cleanup):
    """Recursive delete endpoints remove workflows, campaigns, and their tasks/objects."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"del-camp-{uuid4()}"
    # The test deletes everything itself; this guards against mid-test failures.
    db_cleanup["campaigns"].append(campaign_id)

    # Seed two workflows, one task and one object each.
    wf1_id = None
    wf2_id = None
    with Flowcept(campaign_id=campaign_id, workflow_name=f"del-wf1-{uuid4()}"):
        with FlowceptTask(activity_id="del_task", used={"x": 1}) as t1:
            t1.end(generated={"y": 1})
        Flowcept.db.save_or_update_object(object=b"blob1", object_type="artifact", save_data_in_collection=True)
        wf1_id = Flowcept.current_workflow_id

    with Flowcept(campaign_id=campaign_id, workflow_name=f"del-wf2-{uuid4()}"):
        with FlowceptTask(activity_id="del_task", used={"x": 2}) as t2:
            t2.end(generated={"y": 2})
        Flowcept.db.save_or_update_object(object=b"blob2", object_type="artifact", save_data_in_collection=True)
        wf2_id = Flowcept.current_workflow_id

    assert wf1_id and wf2_id

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": wf1_id}) or []) >= 1)
    assert ok, "Timed out waiting for wf1 tasks."
    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": wf2_id}) or []) >= 1)
    assert ok, "Timed out waiting for wf2 tasks."

    app = create_app()
    client = TestClient(app)

    # Delete wf1 only.
    rs = client.delete(f"/api/v1/workflows/{wf1_id}")
    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["deleted"]["workflows"] >= 1
    assert body["deleted"]["tasks"] >= 1

    # wf1 tasks gone; wf2 intact.
    assert not Flowcept.db.task_query(filter={"workflow_id": wf1_id})
    assert Flowcept.db.task_query(filter={"workflow_id": wf2_id})

    # 404 on nonexistent workflow.
    rs = client.delete("/api/v1/workflows/nonexistent-workflow-id")
    assert rs.status_code == 404, rs.text

    # Delete entire campaign.
    rs = client.delete(f"/api/v1/campaigns/{campaign_id}")
    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["deleted"]["workflows"] >= 1
    assert body["deleted"]["tasks"] >= 1

    # wf2 gone.
    assert not Flowcept.db.task_query(filter={"workflow_id": wf2_id})

    # 404 on repeat.
    rs = client.delete(f"/api/v1/campaigns/{campaign_id}")
    assert rs.status_code == 404, rs.text


def test_delete_also_removes_orphan_agents(db_cleanup):
    """Deleting a workflow removes agents whose tasks are all in that workflow.

    An agent that still has tasks in another workflow must NOT be deleted.
    """
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject

    campaign_id = f"del-agents-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)

    sole_agent_id = f"sole_agent_{uuid4()}"
    shared_agent_id = f"shared_agent_{uuid4()}"

    with Flowcept(campaign_id=campaign_id, workflow_name=f"del-ag-wf1-{uuid4()}"):
        with FlowceptTask(activity_id="act1", used={"x": 1}, agent_id=sole_agent_id) as t:
            t.end(generated={"y": 1})
        with FlowceptTask(activity_id="act2", used={"x": 2}, agent_id=shared_agent_id) as t:
            t.end(generated={"y": 2})
        wf1_id = Flowcept.current_workflow_id

    with Flowcept(campaign_id=campaign_id, workflow_name=f"del-ag-wf2-{uuid4()}"):
        with FlowceptTask(activity_id="act2", used={"x": 3}, agent_id=shared_agent_id) as t:
            t.end(generated={"y": 3})
        wf2_id = Flowcept.current_workflow_id

    assert wf1_id and wf2_id

    # Explicitly register agents in the agents collection.
    Flowcept.db.insert_or_update_agent(
        AgentObject(agent_id=sole_agent_id, name="SoleAgent", workflow_id=wf1_id, campaign_id=campaign_id)
    )
    Flowcept.db.insert_or_update_agent(
        AgentObject(agent_id=shared_agent_id, name="SharedAgent", workflow_id=wf1_id, campaign_id=campaign_id)
    )

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": wf1_id}) or []) >= 2)
    assert ok, "Timed out waiting for wf1 tasks."

    # Both agents must be registered before deleting.
    agents = Flowcept.db.agent_query(filter={"agent_id": {"$in": [sole_agent_id, shared_agent_id]}})
    assert len(agents) == 2, f"Expected 2 agents, got {len(agents or [])}"

    app = create_app()
    client = TestClient(app)

    # Delete wf1 — sole_agent should be removed, shared_agent should stay.
    rs = client.delete(f"/api/v1/workflows/{wf1_id}")
    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["deleted"]["agents"] >= 1

    remaining = Flowcept.db.agent_query(filter={"agent_id": sole_agent_id})
    assert not remaining, "sole_agent should be deleted after its only workflow was deleted"

    remaining = Flowcept.db.agent_query(filter={"agent_id": shared_agent_id})
    assert remaining, "shared_agent must NOT be deleted; it still has tasks in wf2"

    # Delete the campaign — shared_agent should now be removed.
    rs = client.delete(f"/api/v1/campaigns/{campaign_id}")
    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["deleted"]["agents"] >= 1

    remaining = Flowcept.db.agent_query(filter={"agent_id": shared_agent_id})
    assert not remaining, "shared_agent should be deleted after its last workflow was removed"


def test_agent_telemetry_timeseries(db_cleanup):
    """Agent-filtered timeseries returns rows with telemetry for the agent's tasks.

    Regression: TelemetryChart on the agent page showed "No telemetry values
    found" even when the same tasks showed telemetry on the workflow page.
    """
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"tel-camp-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)
    agent_id = f"tel-agent-{uuid4()}"

    with Flowcept(campaign_id=campaign_id, workflow_name=f"tel-wf-{uuid4()}"):
        workflow_id = Flowcept.current_workflow_id
        with FlowceptTask(activity_id="tel_task", used={"x": 1}, agent_id=agent_id) as t:
            t.end(generated={"y": 2})

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 1)
    assert ok, "Timed out waiting for tasks."

    app = create_app()
    client = TestClient(app)

    # Workflow timeseries returns something (baseline — at minimum started_at is set).
    rs = client.post(
        "/api/v1/stats/timeseries",
        json={"filter": {"workflow_id": workflow_id}, "fields": ["started_at"], "x": "started_at"},
    )
    assert rs.status_code == 200
    assert rs.json()["count"] >= 1, "Workflow timeseries found no rows."

    # Agent timeseries with $or filter must also return the task.
    rs = client.post(
        "/api/v1/stats/timeseries",
        json={
            "filter": {"$or": [{"agent_id": agent_id}, {"source_agent_id": agent_id}]},
            "fields": ["started_at"],
            "x": "started_at",
        },
    )
    assert rs.status_code == 200, rs.text
    assert rs.json()["count"] >= 1, (
        "Agent timeseries returned 0 rows even though tasks with agent_id exist. "
        "This is the bug causing 'No telemetry values found' on the agent page."
    )


def test_lmdb_dashboard_roundtrip(tmp_path, monkeypatch):
    """LMDB dashboard CRUD persists and retrieves dashboard documents."""
    from flowcept.configs import LMDB_ENABLED

    if not LMDB_ENABLED:
        pytest.skip("LMDB not enabled.")
    from flowcept.commons.daos.docdb_dao.lmdb_dao import LMDBDAO
    import flowcept.configs as _fc_configs

    monkeypatch.setitem(_fc_configs.LMDB_SETTINGS, "path", str(tmp_path / "lmdb"))
    dao = LMDBDAO()
    doc = {"dashboard_id": "d1", "dashboard_type": "common_workflow", "name": "local", "charts": [], "layout": []}
    assert dao.save_dashboard(doc)
    assert dao.get_dashboard("d1")["name"] == "local"
    assert any(d["dashboard_id"] == "d1" for d in dao.list_dashboards())
    assert dao.list_dashboards(filter={"dashboard_type": "common_workflow"})
    assert dao.delete_dashboard("d1")
    assert dao.get_dashboard("d1") is None
    dao.close()


def test_webservice_dataflow_graph(db_cleanup):
    """PROV-style dataflow over the real Perceptron GridSearch workflow."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    from tests.instrumentation_tests.ml_tests.single_layer_perceptron_test import run_gridsearch_experiment

    campaign_id = f"GridSearchCampaign-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)
    run_data = run_gridsearch_experiment(campaign_id=campaign_id)
    workflow_id = run_data["workflow_id"]
    learning_tasks = [t for t in run_data["tasks"] if t.get("activity_id") == "train_and_validate"]

    ok = _wait_for(
        lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= len(run_data["tasks"])
    )
    assert ok, "Timed out waiting for persisted tasks."

    app = create_app()
    client = TestClient(app)

    # Coarse level (default): per-task input/output chunk entities (PROV Entity vs Activity).
    from flowcept import configs

    original_max = getattr(configs, "WEBSERVER_MAX_LABEL_LENGTH", 30)
    try:
        configs.WEBSERVER_MAX_LABEL_LENGTH = 300
        rs = client.get(f"/api/v1/workflows/{workflow_id}/dataflow")
    finally:
        configs.WEBSERVER_MAX_LABEL_LENGTH = original_max

    assert rs.status_code == 200, rs.text
    body = rs.json()
    assert body["level"] == "coarse"
    task_nodes = [n for n in body["nodes"] if n["kind"] == "task"]
    chunk_nodes = [n for n in body["nodes"] if n["kind"] == "chunk"]
    assert len(task_nodes) == len(run_data["tasks"])
    assert {n["label"] for n in task_nodes} == {
        "call_hpc_agent",
        "get_dataset",
        "submit_gridsearch_job",
        "train_and_validate",
        "select_best_model",
    }
    assert len([n for n in task_nodes if n["label"] == "train_and_validate"]) == len(learning_tasks)
    assert any(n["stats"]["activity_id"] == "train_and_validate" for n in task_nodes)
    assert any(n["stats"]["used"].get("config_id") == "cfg_1" for n in task_nodes)
    assert any("best_val_loss" in n["stats"]["generated"] for n in task_nodes)
    # TDD: Verify task nodes have subtype in their stats
    learning_node = next(n for n in task_nodes if n["label"] == "train_and_validate")
    assert learning_node["stats"].get("subtype") == "learning"
    # Each task with used/generated data is represented as a PROV activity.
    inputs = [c for c in chunk_nodes if c["stats"]["kind"] == "input"]
    outputs = [c for c in chunk_nodes if c["stats"]["kind"] == "output"]
    assert inputs and outputs
    # Chunks pack the key-values; clicking in the UI shows these items.
    assert any(c["stats"]["items"].get("config_id") == "cfg_1" for c in inputs)
    assert any("best_val_loss" in c["stats"]["items"] for c in outputs)
    assert all(c["stats"]["generated_by"] for c in outputs)
    # TDD: Verify chunk labels use key names, never raw arg_N positional keys
    assert any("config_id" in c["label"] for c in inputs)
    assert any("best_val_loss" in c["label"] for c in outputs)
    # submit_gridsearch_job outputs configs list under the key "configs" (not "arg_0")
    submit_node = next(n for n in task_nodes if n["label"] == "submit_gridsearch_job")
    submit_output_chunks = [
        c
        for c in chunk_nodes
        if any(e["source"] == submit_node["id"] and e["target"] == c["id"] for e in body["edges"])
    ]
    assert submit_output_chunks, "submit_gridsearch_job must have output chunks"
    assert all("configs" in c["label"] for c in submit_output_chunks), (
        f"submit_gridsearch_job output chunk labels must use 'configs', got: {[c['label'] for c in submit_output_chunks]}"
    )
    assert not any(re.match(r"^arg_\d+$", c["label"]) for c in chunk_nodes), (
        "No chunk label should be a raw arg_N key — positional keys must use count fallback"
    )
    edges = {(e["source"], e["target"], e["relation"]) for e in body["edges"]}
    for t in task_nodes:
        if t["stats"]["used"]:
            assert any(s.startswith("chunk:") and tgt == t["id"] and r == "used" for (s, tgt, r) in edges)
        if t["stats"]["generated"]:
            assert any(s == t["id"] and tgt.startswith("chunk:") and r == "generated" for (s, tgt, r) in edges)

    # TDD: Verify delegation edge exists from call_hpc_agent task node to submit_gridsearch_job task node
    call_task = next(n for n in task_nodes if n["label"] == "call_hpc_agent")
    submit_task = next(n for n in task_nodes if n["label"] == "submit_gridsearch_job")
    assert any(
        e["source"] == call_task["id"] and e["target"] == submit_task["id"] and e["relation"] == "delegation"
        for e in body["edges"]
    )

    assert not any(n["kind"] == "data" for n in body["nodes"])

    # 404 for unknown workflow.
    rs = client.get("/api/v1/workflows/nonexistent-wf/dataflow")
    assert rs.status_code == 404


def _parse_sse(text: str) -> list:
    r"""Parse a raw SSE response body into a list of {event, data} dicts.

    SSE separates events with \\r\\n\\r\\n (CRLF) or \\n\\n; normalise first.
    """
    events = []
    # Normalise CRLF to LF so block splitting works regardless of transport encoding.
    normalised = text.replace("\r\n", "\n")
    for block in normalised.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        ev: dict = {}
        for line in block.split("\n"):
            if line.startswith("event:"):
                ev["event"] = line[len("event:") :].strip()
            elif line.startswith("data:"):
                raw = line[len("data:") :].strip()
                try:
                    ev["data"] = json.loads(raw)
                except json.JSONDecodeError:
                    ev["data"] = raw
        if ev:
            events.append(ev)
    return events


def test_chat_highlight_lineage_sse(db_cleanup):
    """Full end-to-end: real LLM emits ui:highlight SSE event with the correct seed task IDs.

    Creates a two-task workflow (step_a → step_b via shared data), asks the chat
    endpoint to highlight the lineage of the first task, and verifies the SSE stream
    contains an ``event: ui:highlight`` entry whose ``task_ids`` includes the seed.
    """
    from flowcept.commons.flowcept_logger import FlowceptLogger
    from flowcept.configs import AGENT

    api_key = AGENT.get("api_key")
    if not api_key or api_key in ("?", "your-api-key-here"):
        FlowceptLogger().warning("Skipping real-LLM highlight test: agent.api_key is not set.")
        pytest.skip("agent.api_key is not set.")
    if not AGENT.get("service_provider") or AGENT.get("service_provider") == "?":
        FlowceptLogger().warning("Skipping real-LLM highlight test: agent.service_provider is not set.")
        pytest.skip("agent.service_provider is not set.")
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-hl-camp-{uuid4()}"
    db_cleanup["campaigns"].append(campaign_id)

    # Two-task lineage: step_a generates y=2; step_b uses y=2.
    with Flowcept(campaign_id=campaign_id, workflow_name="hl-lineage-test"):
        wf_id = Flowcept.current_workflow_id
        with FlowceptTask(activity_id="step_a", used={"x": 1}) as task_a:
            task_a.end(generated={"y": 2})
        step_a_id = task_a.get_id()
        with FlowceptTask(activity_id="step_b", used={"y": 2}) as task_b:
            task_b.end(generated={"z": 3})

    assert step_a_id, "step_a task_id must be set after the context exits."

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": wf_id}) or []) >= 2)
    assert ok, "Timed out waiting for tasks to be persisted."

    # LLMs can be non-deterministic about tool calls; retry up to 3 times.
    # Each attempt recreates the app+client to avoid sse_starlette's AppStatus
    # event-loop binding issue (should_exit_event is a module-level singleton that
    # gets bound to the first event loop; a fresh Event() avoids the RuntimeError
    # on the second call in the same process).
    import asyncio
    from sse_starlette.sse import AppStatus

    highlight_events = []
    last_event_names = []
    for attempt in range(3):
        AppStatus.should_exit_event = asyncio.Event()
        app = create_app()
        client = TestClient(app)
        rs = client.post(
            "/api/v1/chat",
            json={
                "messages": [
                    {
                        "role": "user",
                        "content": f"Highlight the lineage of task {step_a_id} in the dataflow graph using the highlight_lineage tool.",
                    }
                ],
                "context": {"workflow_id": wf_id},
                "stream": True,
            },
        )
        assert rs.status_code == 200, rs.text
        events = _parse_sse(rs.text)
        last_event_names = [e.get("event") for e in events]
        highlight_events = [e for e in events if e.get("event") == "ui:highlight"]
        if highlight_events:
            break
        FlowceptLogger().warning(f"highlight attempt {attempt + 1}: no ui:highlight yet (events={last_event_names})")

    assert highlight_events, (
        f"Expected a 'ui:highlight' SSE event in 3 attempts but got: {last_event_names}. "
        "Check the system prompt and tool binding."
    )
    task_ids_in_highlight = highlight_events[0]["data"].get("task_ids", [])
    assert step_a_id in task_ids_in_highlight, (
        f"Expected seed task {step_a_id} in ui:highlight task_ids={task_ids_in_highlight}"
    )

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_node_positions_endpoint(db_cleanup):
    """Test saving and loading node positions via FastAPI REST endpoints."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    workflow_id = f"wf-pos-test-{uuid4()}"
    db_cleanup["workflows"].append(workflow_id)

    # Insert a dummy workflow so the ID exists/cleans up nicely
    wf = WorkflowObject()
    wf.workflow_id = workflow_id
    Flowcept.db.insert_or_update_workflow(wf)

    app = create_app()
    client = TestClient(app)

    # 1. Fetch positions for a non-existent position mapping (should be empty dict)
    rs = client.get(f"/api/v1/workflows/{workflow_id}/node_positions?graph_type=dataflow")
    assert rs.status_code == 200
    assert rs.json() == {}

    # 2. Save positions
    pos_data = {
        "graph_type": "dataflow",
        "positions": {"node-1": {"x": 12.5, "y": 45.6}, "node-2": {"x": 78.9, "y": 101.2}},
    }
    rs = client.post(f"/api/v1/workflows/{workflow_id}/node_positions", json=pos_data)
    assert rs.status_code == 200
    assert rs.json() == {"success": True}

    # 3. Retrieve positions and verify
    rs = client.get(f"/api/v1/workflows/{workflow_id}/node_positions?graph_type=dataflow")
    assert rs.status_code == 200
    retrieved = rs.json()
    assert retrieved["node-1"] == {"x": 12.5, "y": 45.6}
    assert retrieved["node-2"] == {"x": 78.9, "y": 101.2}


def test_agents_without_tasks_are_not_returned(db_cleanup):
    """TDD test: agents with 0 tasks must be filtered out and not listed."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive.")

    from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject

    empty_agent_id = f"empty-agent-{uuid4()}"

    agent = AgentObject()
    agent.agent_id = empty_agent_id
    agent.name = "EmptyAgent"
    Flowcept.db.insert_or_update_agent(agent)

    app = create_app()
    client = TestClient(app)

    rs = client.get("/api/v1/agents")
    assert rs.status_code == 200
    items = rs.json()["items"]
    assert not any(item["agent_id"] == empty_agent_id for item in items)
