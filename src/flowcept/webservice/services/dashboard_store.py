"""Dashboard persistence: MongoDB collection when available, JSON files otherwise."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, List, Optional

from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import WEBSERVER_DASHBOARDS_DIR

_SEED_FILE = Path(__file__).parent.parent / "ui_build" / "default_dashboard_configs.json"


class MongoDashboardStore:
    """Dashboard store backed by the ``dashboards`` MongoDB collection."""

    def __init__(self, dao):
        self._dao = dao

    def save(self, dashboard: Dict) -> bool:
        """Insert or replace a dashboard document."""
        return self._dao.save_dashboard(dashboard)

    def get(self, dashboard_id: str) -> Optional[Dict]:
        """Get a dashboard document by id."""
        return self._dao.get_dashboard(dashboard_id)

    def list(self) -> List[Dict]:
        """List all dashboard documents, seeding defaults if the collection is empty."""
        docs = self._dao.list_dashboards() or []
        if not docs:
            docs = self._seed()
        return docs

    def list_by_type(self, dashboard_type: str) -> List[Dict]:
        """List dashboard documents of a specific type."""
        self.list()  # ensure seeded
        return self._dao.list_dashboards(filter={"dashboard_type": dashboard_type}) or []

    def delete(self, dashboard_id: str) -> bool:
        """Delete a dashboard document by id."""
        return self._dao.delete_dashboard(dashboard_id)

    def _seed(self) -> List[Dict]:
        """Load default configs from the bundled JSON file and persist them."""
        if not _SEED_FILE.exists():
            FlowceptLogger().warning(f"Default dashboard configs not found at {_SEED_FILE}")
            return []
        try:
            with open(_SEED_FILE) as f:
                configs = json.load(f)
            for doc in configs:
                self._dao.save_dashboard(doc)
            return configs
        except Exception as e:
            FlowceptLogger().exception(e)
            return []


class FileDashboardStore:
    """Dashboard store writing one JSON file per dashboard under a local directory."""

    def __init__(self, directory: str = WEBSERVER_DASHBOARDS_DIR):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self.logger = FlowceptLogger()

    def _path(self, dashboard_id: str) -> Path:
        safe = "".join(c for c in dashboard_id if c.isalnum() or c in "-_")
        return self._dir / f"{safe}.json"

    def save(self, dashboard: Dict) -> bool:
        """Insert or replace a dashboard JSON file."""
        try:
            with open(self._path(dashboard["dashboard_id"]), "w") as handle:
                json.dump(dashboard, handle, indent=2)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def get(self, dashboard_id: str) -> Optional[Dict]:
        """Get a dashboard from its JSON file."""
        path = self._path(dashboard_id)
        if not path.exists():
            return None
        try:
            with open(path) as handle:
                return json.load(handle)
        except Exception as e:
            self.logger.exception(e)
            return None

    def list(self) -> List[Dict]:
        """List all dashboards, seeding defaults if the directory is empty."""
        docs = self._load_all()
        if not docs:
            docs = self._seed()
        return docs

    def list_by_type(self, dashboard_type: str) -> List[Dict]:
        """List dashboards of a specific type."""
        self.list()  # ensure seeded
        return [d for d in self._load_all() if d.get("dashboard_type") == dashboard_type]

    def delete(self, dashboard_id: str) -> bool:
        """Delete a dashboard JSON file."""
        path = self._path(dashboard_id)
        if not path.exists():
            return False
        try:
            os.remove(path)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def _load_all(self) -> List[Dict]:
        dashboards = []
        for path in sorted(self._dir.glob("*.json")):
            try:
                with open(path) as handle:
                    dashboards.append(json.load(handle))
            except Exception as e:
                self.logger.exception(e)
        return dashboards

    def _seed(self) -> List[Dict]:
        """Load default configs from the bundled JSON file and persist them."""
        if not _SEED_FILE.exists():
            self.logger.warning(f"Default dashboard configs not found at {_SEED_FILE}")
            return []
        try:
            with open(_SEED_FILE) as f:
                configs = json.load(f)
            for doc in configs:
                self.save(doc)
            return configs
        except Exception as e:
            self.logger.exception(e)
            return []


def get_dashboard_store():
    """Return the dashboard store for the configured DocDB backend.

    Mongo-backed deployments store dashboards in a ``dashboards`` collection;
    other backends fall back to JSON files under ``web_server.dashboards_dir``.
    """
    dao = DocumentDBDAO.get_instance(create_indices=False)
    if hasattr(dao, "save_dashboard"):
        return MongoDashboardStore(dao)
    return FileDashboardStore()
