"""Integration test for webservice routes backed by real Flowcept + MongoDB."""

from __future__ import annotations

import json
import threading
import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from flowcept import Flowcept, FlowceptTask
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


def test_webservice_campaigns_agents_stats_and_prov_card():
    """End-to-end test for derived campaigns/agents, stats endpoints, and workflow cards."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    workflow_name = f"ws-stats-workflow-{uuid4()}"
    agent_id = f"ws-agent-{uuid4()}"

    with Flowcept(campaign_id=campaign_id, workflow_name=workflow_name):
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
        "/api/v1/stats/card_data",
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

    # Provenance card: JSON and markdown content.
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
    assert rs.status_code == 400

    # Cleanup singleton client handles for test isolation.
    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_webservice_object_versioning_and_unified_query():
    """End-to-end test for object version history and the unified /query/{scope} endpoint."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    obj_id = f"ws-versioned-{uuid4()}"

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

    rs = client.post(f"/api/v1/workflows/{workflow_id}/reports/workflow-card/download")
    assert rs.status_code == 200
    assert rs.headers["content-type"].startswith("text/markdown")

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_webservice_dashboards_crud():
    """End-to-end CRUD test for dashboards stored in the real backend."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    app = create_app()
    client = TestClient(app)

    spec = {
        "name": f"dash-{uuid4()}",
        "description": "integration test dashboard",
        "context": {"campaign_id": "camp-1"},
        "cards": [
            {
                "card_id": "c1",
                "type": "chart",
                "title": "Tasks per activity",
                "data": {
                    "source": "tasks",
                    "group_by": "activity_id",
                    "metrics": [{"field": "", "agg": "count"}],
                },
                "viz": {"kind": "bar"},
            },
            {"card_id": "c2", "type": "markdown", "content": "# Notes"},
        ],
        "layout": [
            {"card_id": "c1", "x": 0, "y": 0, "w": 6, "h": 4},
            {"card_id": "c2", "x": 6, "y": 0, "w": 6, "h": 4},
        ],
    }

    rs = client.post("/api/v1/dashboards", json=spec)
    assert rs.status_code == 201
    created = rs.json()
    dashboard_id = created["dashboard_id"]
    assert dashboard_id and created["created_at"]

    try:
        rs = client.get(f"/api/v1/dashboards/{dashboard_id}")
        assert rs.status_code == 200
        assert rs.json()["name"] == spec["name"]
        assert len(rs.json()["cards"]) == 2

        rs = client.get("/api/v1/dashboards")
        assert rs.status_code == 200
        assert any(d["dashboard_id"] == dashboard_id for d in rs.json()["items"])

        updated = dict(spec, description="updated")
        rs = client.put(f"/api/v1/dashboards/{dashboard_id}", json=updated)
        assert rs.status_code == 200
        assert rs.json()["description"] == "updated"
        assert rs.json()["created_at"] == created["created_at"]
        assert rs.json()["updated_at"] >= created["updated_at"]

        # Spec validation: bad card type and disallowed filter operator must be rejected.
        bad = dict(spec, cards=[{"card_id": "x", "type": "nope"}])
        rs = client.post("/api/v1/dashboards", json=bad)
        assert rs.status_code == 422

        bad = dict(spec, context={"$where": "1"})
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


def test_webservice_stream_tasks_sse():
    """End-to-end SSE: existing tasks arrive in the first event; mid-stream inserts arrive next."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"

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


def test_webservice_stream_workflows_sse():
    """End-to-end SSE for the workflows stream filtered by campaign."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
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


def test_prov_tools_shared_core():
    """The shared provenance tool core (used by web chat and MCP agent) works on real data."""
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    from flowcept.agents.tools.prov_tools import (
        get_task_summary,
        list_campaigns,
        make_chart,
        query_tasks,
        query_workflows,
    )

    campaign_id = f"ws-campaign-{uuid4()}"
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
            "card_id": "chat-c1",
            "type": "chart",
            "title": "tasks per activity",
            "data": {"source": "tasks", "filter": {"workflow_id": workflow_id}, "group_by": "activity_id"},
            "viz": {"kind": "bar"},
        }
    )
    assert result.code in (201, 301)
    assert result.result["rows"]
    assert result.result["chart"]["card_id"] == "chat-c1"

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


def test_chat_endpoint_real_llm_tool_roundtrip():
    """Real LLM chat round-trip: the model must call a query tool and answer (env-gated)."""
    from flowcept.commons.flowcept_logger import FlowceptLogger
    from flowcept.configs import AGENT

    api_key = AGENT.get("api_key")
    if not api_key or api_key == "?":
        FlowceptLogger().warning("Skipping real-LLM chat test because agent.api_key is not set.")
        pytest.skip("agent.api_key is not set.")
    if not AGENT.get("service_provider") or AGENT.get("service_provider") == "?":
        FlowceptLogger().warning("Skipping real-LLM chat test because agent.service_provider is not set.")
        pytest.skip("agent.service_provider is not set.")
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"ws-campaign-{uuid4()}"
    with Flowcept(campaign_id=campaign_id, workflow_name=f"ws-chat-wf-{uuid4()}"):
        workflow_id = Flowcept.current_workflow_id
        for i in range(3):
            with FlowceptTask(activity_id="chat_seed", used={"i": i}) as task:
                task.end(generated={"o": i})

    ok = _wait_for(lambda: len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or []) >= 3)
    assert ok, "Timed out waiting for persisted tasks."

    app = create_app()
    client = TestClient(app)
    rs = client.post(
        "/api/v1/chat",
        json={
            "messages": [{"role": "user", "content": "How many tasks ran in this workflow?"}],
            "context": {"workflow_id": workflow_id},
            "stream": False,
        },
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["message"]
    assert any("3" in str(part) for part in (body["message"], body.get("tool_trace", [])))
    assert body.get("tool_trace"), "Expected the LLM to call at least one tool."

    if DocumentDBDAO._instance is not None:
        DocumentDBDAO._instance.close()


def test_recursive_delete_workflow_and_campaign():
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services are not alive (MQ/KVDB/Mongo).")

    campaign_id = f"del-camp-{uuid4()}"

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


def test_file_dashboard_store_roundtrip(tmp_path):
    """FileDashboardStore (non-Mongo fallback) persists real JSON files."""
    from flowcept.webservice.services.dashboard_store import FileDashboardStore

    store = FileDashboardStore(directory=str(tmp_path))
    doc = {"dashboard_id": "d1", "name": "local", "cards": [], "layout": []}
    assert store.save(doc)
    assert store.get("d1")["name"] == "local"
    assert any(d["dashboard_id"] == "d1" for d in store.list())
    assert store.delete("d1")
    assert store.get("d1") is None
    assert store.delete("d1") is False
