"""Webservice API tests with a mocked DBAPI dependency."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from flowcept.commons.flowcept_dataclasses.blob_object import BlobObject
from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.main import create_app
from flowcept.webservice.services.dashboard_store import get_dashboard_store


class FakeDB:
    """Simple fake DBAPI for endpoint tests."""

    def __init__(self):
        self.workflows = [
            {"workflow_id": "wf-1", "user": "alice", "campaign_id": "c1", "name": "run-a", "utc_timestamp": 200},
            {"workflow_id": "wf-2", "user": "bob", "campaign_id": "c2", "name": "run-b", "utc_timestamp": 100},
        ]
        self.tasks = [
            {"task_id": "t2", "workflow_id": "wf-1", "status": "running", "started_at": 20},
            {"task_id": "t1", "workflow_id": "wf-1", "status": "finished", "started_at": 10},
            {"task_id": "t3", "workflow_id": "wf-2", "status": "finished", "started_at": 30},
        ]
        self.agents = []
        self.objects = [
            {
                "object_id": "o1",
                "workflow_id": "wf-1",
                "task_id": "t1",
                "object_type": "dataset",
                "version": 1,
                "custom_metadata": {"k": "v1"},
                "data": b"payload-1",
                "created_at": "2025-01-02T00:00:00",
            },
            {
                "object_id": "o2",
                "workflow_id": "wf-2",
                "task_id": "t3",
                "object_type": "ml_model",
                "version": 2,
                "custom_metadata": {"k": "v2", "loss": 0.42},
                "data": b"payload-2",
                "created_at": "2025-01-01T00:00:00",
            },
            {
                "object_id": "o3",
                "workflow_id": "wf-1",
                "task_id": "t2",
                "object_type": "ml_model",
                "version": 3,
                "custom_metadata": {"k": "v3", "loss": 0.11},
                "data": b"payload-2",
                "created_at": "2025-01-01T00:00:00",
            },
        ]

    @staticmethod
    def _nested_get(item, field):
        value = item
        for part in field.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    @classmethod
    def _matches_filter(cls, item, filter_doc):
        if not filter_doc:
            return True

        for key, value in filter_doc.items():
            if key == "$and":
                return all(cls._matches_filter(item, clause) for clause in value)
            if key == "$or":
                return any(cls._matches_filter(item, clause) for clause in value)

            field_value = cls._nested_get(item, key)
            if isinstance(value, dict):
                for op, expected in value.items():
                    if op == "$exists":
                        exists = field_value is not None
                        if bool(expected) != exists:
                            return False
                    elif op == "$eq":
                        if field_value != expected:
                            return False
                    elif op == "$ne":
                        if field_value == expected:
                            return False
                    elif op == "$in":
                        if field_value not in expected:
                            return False
                    elif op == "$nin":
                        if field_value in expected:
                            return False
                    elif op == "$gt":
                        if field_value is None or not field_value > expected:
                            return False
                    elif op == "$gte":
                        if field_value is None or not field_value >= expected:
                            return False
                    elif op == "$lt":
                        if field_value is None or not field_value < expected:
                            return False
                    elif op == "$lte":
                        if field_value is None or not field_value <= expected:
                            return False
                    else:
                        raise ValueError(f"Unsupported fake operator in test DB: {op}")
            else:
                if field_value != value:
                    return False
        return True

    def workflow_query(self, filter):
        return [wf for wf in self.workflows if self._matches_filter(wf, filter)]

    def get_workflow_object(self, workflow_id):
        for wf in self.workflows:
            if wf["workflow_id"] == workflow_id:
                return WorkflowObject.from_dict(wf)
        return None

    def query(self, **kwargs):
        collection = kwargs.get("collection")
        filter_ = kwargs.get("filter") or {}
        limit = kwargs.get("limit", 0)
        projection = kwargs.get("projection")
        sort = kwargs.get("sort")

        if collection == "workflows":
            rs = [wf for wf in self.workflows if self._matches_filter(wf, filter_)]
            if sort:
                for field, order in reversed(sort):
                    rs = sorted(rs, key=lambda item: self._nested_get(item, field), reverse=(order == -1))
            if projection:
                rs = [{k: v for k, v in row.items() if k in projection} for row in rs]
            return rs[:limit] if limit else rs

        if collection == "objects":
            rs = [obj for obj in self.objects if self._matches_filter(obj, filter_)]
            if sort:
                for field, order in reversed(sort):
                    rs = sorted(rs, key=lambda item: self._nested_get(item, field), reverse=(order == -1))
            if projection:
                rs = [{k: v for k, v in row.items() if k in projection} for row in rs]
            return rs[:limit] if limit else rs

        if collection == "tasks":
            rs = [task for task in self.tasks if self._matches_filter(task, filter_)]
            if sort:
                for field, order in reversed(sort):
                    rs = sorted(rs, key=lambda item: self._nested_get(item, field), reverse=(order == -1))
            if projection:
                rs = [{k: v for k, v in row.items() if k in projection} for row in rs]
            return rs[:limit] if limit else rs

        if collection == "agents":
            rs = [ag for ag in self.agents if self._matches_filter(ag, filter_)]
            if sort:
                for field, order in reversed(sort):
                    rs = sorted(rs, key=lambda item: self._nested_get(item, field), reverse=(order == -1))
            if projection:
                rs = [{k: v for k, v in row.items() if k in projection} for row in rs]
            return rs[:limit] if limit else rs

        return []

    def agent_query(
        self,
        filter,
        projection=None,
        limit=0,
        sort=None,
    ):
        rs = [ag for ag in self.agents if self._matches_filter(ag, filter or {})]
        if sort:
            for field, order in reversed(sort):
                rs = sorted(rs, key=lambda item: item.get(field), reverse=(order == -1))
        if projection:
            rs = [{k: v for k, v in row.items() if k in projection} for row in rs]
        return rs[:limit] if limit else rs

    def task_query(
        self,
        filter,
        projection=None,
        limit=0,
        sort=None,
        aggregation=None,
        remove_json_unserializables=True,
    ):
        rs = [task for task in self.tasks if self._matches_filter(task, filter or {})]

        if sort:
            for field, order in reversed(sort):
                rs = sorted(rs, key=lambda item: item.get(field), reverse=(order == -1))

        if projection:
            rs = [{k: v for k, v in row.items() if k in projection} for row in rs]

        return rs[:limit] if limit else rs

    def blob_object_query(self, filter):
        return [obj for obj in self.objects if self._matches_filter(obj, filter or {})]

    def get_blob_object(self, object_id, version=None):
        if version is None:
            for obj in self.objects:
                if obj["object_id"] == object_id:
                    return BlobObject.from_dict(obj)
            raise ValueError(f"Object not found for object_id={object_id}.")

        for obj in self.objects:
            if obj["object_id"] == object_id and obj["version"] == version:
                return BlobObject.from_dict(obj)

        raise ValueError(f"Object not found for object_id={object_id}, version={version}.")

    def get_object_history(self, object_id):
        return [
            {"object_id": object_id, "version": 2, "created_at": "2025-01-02T00:00:00"},
            {"object_id": object_id, "version": 1, "created_at": "2025-01-01T00:00:00"},
        ]


def build_client() -> tuple[TestClient, FakeDB]:
    app = create_app()
    fake_db = FakeDB()
    app.dependency_overrides[get_db_api] = lambda: fake_db
    return TestClient(app), fake_db


class FakeDashboardStore:
    """Small in-memory dashboard store for route contract tests."""

    def __init__(self):
        self.docs = {}

    def save(self, dashboard):
        self.docs[dashboard["dashboard_id"]] = dashboard
        return True

    def get(self, dashboard_id):
        return self.docs.get(dashboard_id)

    def list(self):
        return list(self.docs.values())

    def list_by_type(self, dashboard_type):
        return [doc for doc in self.docs.values() if doc.get("dashboard_type") == dashboard_type]

    def delete(self, dashboard_id):
        return self.docs.pop(dashboard_id, None) is not None


def test_info_endpoint():
    from flowcept.version import __version__

    client, _ = build_client()
    rs = client.get("/api/v1/info")
    assert rs.status_code == 200
    assert rs.json() == {"service": "flowcept", "version": __version__}


def test_root_and_openapi_endpoints():
    client, _ = build_client()

    root = client.get("/")
    assert root.status_code == 200
    if root.headers["content-type"].startswith("application/json"):
        # No built UI assets present: root exposes the API status payload.
        assert root.json()["service"] == "flowcept-webservice"
    else:
        # Built UI assets present: root serves the SPA index page.
        assert "text/html" in root.headers["content-type"]

    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200


def test_health_endpoints():
    client, _ = build_client()
    assert client.get("/api/v1/health/live").json() == {"status": "ok"}
    assert client.get("/api/v1/health/ready").json() == {"status": "ready"}


def test_workflows_list_get_and_query():
    client, _ = build_client()

    rs = client.get("/api/v1/workflows", params={"limit": 10})
    assert rs.status_code == 200
    items = rs.json()["items"]
    assert [item["workflow_id"] for item in items] == ["wf-1", "wf-2"]

    rs = client.get("/api/v1/workflows", params={"user": "alice", "limit": 5})
    assert rs.status_code == 200
    body = rs.json()
    assert body["count"] == 1
    assert body["items"][0]["workflow_id"] == "wf-1"

    rs = client.get("/api/v1/workflows/wf-1")
    assert rs.status_code == 200
    assert rs.json()["workflow_id"] == "wf-1"

    rs = client.post(
        "/api/v1/workflows/query",
        json={"filter": {"campaign_id": "c2"}, "limit": 10, "projection": ["workflow_id"]},
    )
    assert rs.status_code == 200
    assert rs.json()["count"] == 1


def test_workflow_card_download_route():
    client, _ = build_client()

    def _fake_generate_report(**kwargs):
        output = kwargs["output_path"]
        Path(output).write_text("# Workflow Card\n\nworkflow: wf-1\n", encoding="utf-8")
        return {"output": output}

    with patch("flowcept.webservice.routers.workflows.Flowcept.generate_report", side_effect=_fake_generate_report):
        rs = client.post("/api/v1/workflows/wf-1/reports/workflow-card/download")

    assert rs.status_code == 200
    assert rs.headers["content-type"].startswith("text/markdown")
    assert 'attachment; filename="workflow_card_wf-1.md"' == rs.headers["content-disposition"]
    assert "# Workflow Card" in rs.text


def test_workflow_card_pdf_download_route():
    client, _ = build_client()

    def _fake_generate_report(**kwargs):
        output = kwargs["output_path"]
        Path(output).write_bytes(b"%PDF-1.4\n%%EOF")
        return {"output": output}

    with patch("flowcept.webservice.services.reports.generate_report", side_effect=_fake_generate_report):
        rs = client.get("/api/v1/workflows/wf-1/workflow_card", params={"format": "pdf"})

    assert rs.status_code == 200
    assert rs.headers["content-type"].startswith("application/pdf")
    assert rs.headers["content-disposition"] == 'attachment; filename="workflow_card_wf-1.pdf"'
    assert rs.content.startswith(b"%PDF-1.4")


def test_workflow_card_route_is_named_workflow_card():
    client, _ = build_client()

    openapi = client.get("/openapi.json")
    assert openapi.status_code == 200
    schema = openapi.json()
    paths = schema["paths"]
    assert "/api/v1/workflows/{workflow_id}/workflow_card" in paths
    assert "/api/v1/workflows/{workflow_id}/provenance_card" not in paths


def test_workflows_errors():
    client, _ = build_client()

    rs = client.get("/api/v1/workflows/does-not-exist")
    assert rs.status_code == 404

    rs = client.get("/api/v1/workflows", params={"filter_json": "not-json"})
    assert rs.status_code == 400

    rs = client.post("/api/v1/workflows/does-not-exist/reports/workflow-card/download")
    assert rs.status_code == 404


def test_workflow_card_download_generation_error():
    client, _ = build_client()

    with patch(
        "flowcept.webservice.routers.workflows.Flowcept.generate_report",
        side_effect=RuntimeError("report generation failed"),
    ):
        rs = client.post("/api/v1/workflows/wf-1/reports/workflow-card/download")

    assert rs.status_code == 500
    assert "Could not generate workflow card" in rs.json()["detail"]


def test_tasks_list_get_by_workflow_and_query():
    client, _ = build_client()

    rs = client.get("/api/v1/tasks", params={"workflow_id": "wf-1", "limit": 10})
    assert rs.status_code == 200
    assert rs.json()["count"] == 2
    assert [item["task_id"] for item in rs.json()["items"]] == ["t2", "t1"]

    rs = client.get("/api/v1/tasks/t1")
    assert rs.status_code == 200
    assert rs.json()["task_id"] == "t1"

    rs = client.get("/api/v1/tasks/by_workflow/wf-2")
    assert rs.status_code == 200
    assert rs.json()["count"] == 1

    rs = client.post(
        "/api/v1/tasks/query",
        json={
            "filter": {"workflow_id": "wf-1"},
            "sort": [{"field": "started_at", "order": -1}],
            "projection": ["task_id", "started_at"],
            "limit": 10,
        },
    )
    assert rs.status_code == 200
    items = rs.json()["items"]
    assert items[0]["started_at"] >= items[1]["started_at"]


def test_tasks_errors_and_validation():
    client, _ = build_client()

    rs = client.get("/api/v1/tasks/")
    assert rs.status_code == 404

    rs = client.get("/api/v1/tasks/missing")
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


def test_objects_list_get_version_history_and_query():
    client, _ = build_client()

    rs = client.get("/api/v1/objects", params={"workflow_id": "wf-1", "limit": 10})
    assert rs.status_code == 200
    assert rs.json()["count"] == 2
    assert "data" not in rs.json()["items"][0]

    rs = client.get("/api/v1/objects", params={"limit": 10})
    assert rs.status_code == 200
    assert [item["object_id"] for item in rs.json()["items"]] == ["o1", "o2", "o3"]

    rs = client.get("/api/v1/objects/o1")
    assert rs.status_code == 200
    assert rs.json()["object_id"] == "o1"
    assert "data" not in rs.json()

    rs = client.get("/api/v1/objects/o1", params={"include_data": True})
    assert rs.status_code == 200
    assert isinstance(rs.json()["data"], str)

    rs = client.get("/api/v1/objects/o2/versions/2", params={"include_data": True})
    assert rs.status_code == 200
    assert rs.json()["version"] == 2

    rs = client.get("/api/v1/objects/o1/download")
    assert rs.status_code == 200
    assert rs.content == b"payload-1"

    rs = client.get("/api/v1/objects/o2/versions/2/download")
    assert rs.status_code == 200
    assert rs.content == b"payload-2"

    rs = client.get("/api/v1/objects/o2/history", params={"limit": 1})
    assert rs.status_code == 200
    assert rs.json()["count"] == 1

    rs = client.post(
        "/api/v1/objects/query",
        json={
            "filter": {},
            "projection": ["object_id", "version"],
            "sort": [{"field": "version", "order": -1}],
            "limit": 1,
            "include_data": False,
        },
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["count"] == 1
    assert set(body["items"][0].keys()) <= {"object_id", "version"}


def test_objects_errors_and_validation():
    client, _ = build_client()

    rs = client.get("/api/v1/objects/unknown")
    assert rs.status_code == 404

    rs = client.get("/api/v1/objects/o1/versions/99")
    assert rs.status_code == 404

    rs = client.get("/api/v1/objects", params={"filter_json": "not-json"})
    assert rs.status_code == 400

    rs = client.post("/api/v1/objects/query", json={"filter": {}, "limit": 5001})
    assert rs.status_code == 422


def test_datasets_routes():
    client, _ = build_client()

    rs = client.get("/api/v1/datasets")
    assert rs.status_code == 200
    assert rs.json()["count"] == 1
    assert rs.json()["items"][0]["object_type"] == "dataset"

    rs = client.get("/api/v1/datasets/o1")
    assert rs.status_code == 200
    assert rs.json()["object_type"] == "dataset"

    rs = client.get("/api/v1/datasets/o1/versions/1")
    assert rs.status_code == 200
    assert rs.json()["version"] == 1

    rs = client.get("/api/v1/datasets/o1/download")
    assert rs.status_code == 200
    assert rs.content == b"payload-1"

    rs = client.post("/api/v1/datasets/query", json={"filter": {}, "limit": 10})
    assert rs.status_code == 200
    assert rs.json()["count"] == 1
    assert rs.json()["items"][0]["object_type"] == "dataset"

    rs = client.get("/api/v1/datasets/o2")
    assert rs.status_code == 404


def test_models_routes():
    client, _ = build_client()

    rs = client.get("/api/v1/models")
    assert rs.status_code == 200
    assert rs.json()["count"] == 2
    assert rs.json()["items"][0]["object_type"] == "ml_model"

    rs = client.get("/api/v1/models/o2")
    assert rs.status_code == 200
    assert rs.json()["object_type"] == "ml_model"

    rs = client.get("/api/v1/models/o2/versions/2")
    assert rs.status_code == 200
    assert rs.json()["version"] == 2

    rs = client.get("/api/v1/models/o2/download")
    assert rs.status_code == 200
    assert rs.content == b"payload-2"

    rs = client.post("/api/v1/models/query", json={"filter": {}, "limit": 10})
    assert rs.status_code == 200
    assert rs.json()["count"] == 2
    assert rs.json()["items"][0]["object_type"] == "ml_model"

    rs = client.get("/api/v1/models/o1")
    assert rs.status_code == 404


def test_unified_scoped_query_models_supports_exists_and_nested_sort():
    client, _ = build_client()

    rs = client.post(
        "/api/v1/query/models",
        json={
            "filter": {
                "workflow_id": "wf-1",
                "custom_metadata.loss": {"$exists": True},
            },
            "sort": [{"field": "custom_metadata.loss", "order": 1}],
            "projection": ["object_id", "object_type", "custom_metadata"],
            "limit": 1,
        },
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["count"] == 1
    assert body["items"][0]["object_id"] == "o3"
    assert body["items"][0]["object_type"] == "ml_model"
    assert body["items"][0]["custom_metadata"]["loss"] == 0.11


def test_unified_scoped_query_workflows_scope():
    client, _ = build_client()
    rs = client.post(
        "/api/v1/query/workflows",
        json={
            "filter": {"campaign_id": "c1"},
            "projection": ["workflow_id", "campaign_id"],
            "limit": 10,
        },
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["count"] == 1
    assert body["items"][0]["workflow_id"] == "wf-1"


def test_unified_scoped_query_tasks_scope():
    client, _ = build_client()
    rs = client.post(
        "/api/v1/query/tasks",
        json={
            "filter": {"workflow_id": "wf-1"},
            "sort": [{"field": "started_at", "order": -1}],
            "projection": ["task_id", "started_at"],
            "limit": 1,
        },
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["count"] == 1
    assert body["items"][0]["task_id"] == "t2"


def test_unified_scoped_query_objects_scope():
    client, _ = build_client()
    rs = client.post(
        "/api/v1/query/objects",
        json={
            "filter": {"object_type": "dataset"},
            "projection": ["object_id", "object_type"],
            "limit": 10,
        },
    )
    assert rs.status_code == 200
    body = rs.json()
    assert body["count"] == 1
    assert body["items"][0]["object_id"] == "o1"
    assert body["items"][0]["object_type"] == "dataset"


def test_unified_scoped_query_datasets_scope_enforces_type():
    client, _ = build_client()
    rs = client.post(
        "/api/v1/query/datasets",
        json={
            "filter": {"object_type": "ml_model"},
            "limit": 10,
        },
    )
    assert rs.status_code == 200
    assert rs.json()["count"] == 0


def test_unified_scoped_query_rejects_unsupported_operator():
    client, _ = build_client()
    rs = client.post(
        "/api/v1/query/objects",
        json={
            "filter": {"task_id": {"$where": "this.task_id == 't1'"}},
            "limit": 10,
        },
    )
    assert rs.status_code == 400
    assert "Unsupported filter operator" in rs.json()["detail"]


def test_dashboard_routes_accept_charts_contract():
    app = create_app()
    store = FakeDashboardStore()
    app.dependency_overrides[get_dashboard_store] = lambda: store
    client = TestClient(app)

    spec = {
        "name": "dashboard",
        "context": {"workflow_id": "wf-1"},
        "charts": [
            {
                "chart_id": "c1",
                "type": "chart",
                "data": {"source": "tasks", "filter": {"workflow_id": "wf-1"}},
            }
        ],
        "layout": [{"chart_id": "c1", "x": 0, "y": 0, "w": 6, "h": 4}],
    }

    rs = client.post("/api/v1/dashboards", json=spec)
    assert rs.status_code == 201
    body = rs.json()
    assert body["charts"][0]["chart_id"] == "c1"
    assert body["layout"][0]["chart_id"] == "c1"


def test_agents_and_dataflow_routes():
    client, fake_db = build_client()

    fake_db.tasks = [
        {
            "task_id": "t1",
            "workflow_id": "wf-1",
            "status": "finished",
            "started_at": 10,
            "agent_id": "agent-1",
            "source_agent_id": "orchestrator",
            "used": {"x": 1},
            "generated": {"y": 2},
        },
        {
            "task_id": "t2",
            "workflow_id": "wf-1",
            "status": "running",
            "started_at": 20,
            "agent_id": "agent-2",
            "used": {"y": 2},
            "generated": {"z": 3},
        },
    ]
    fake_db.agents = [
        {"agent_id": "agent-1", "name": "Agent 1", "registered_at": 10},
        {"agent_id": "agent-2", "name": "Agent 2", "registered_at": 20},
    ]

    rs = client.get("/api/v1/agents")
    assert rs.status_code == 200
    agents = rs.json()["items"]
    assert len(agents) == 2
    agent_map = {a["agent_id"]: a for a in agents}
    assert "agent-1" in agent_map
    assert "agent-2" in agent_map

    rs = client.get("/api/v1/agents/agent-1")
    assert rs.status_code == 200
    assert rs.json()["agent"]["agent_id"] == "agent-1"

    rs = client.get("/api/v1/workflows/wf-1/dataflow")
    assert rs.status_code == 200
    dataflow = rs.json()
    task_nodes = [n for n in dataflow["nodes"] if n["kind"] == "task"]
    assert len(task_nodes) == 2
    for node in task_nodes:
        stats = node["stats"]
        assert "agent_id" in stats
        assert "source_agent_id" in stats
        if node["id"] == "task:t1":
            assert stats["agent_id"] == "agent-1"
            assert stats["source_agent_id"] == "orchestrator"
