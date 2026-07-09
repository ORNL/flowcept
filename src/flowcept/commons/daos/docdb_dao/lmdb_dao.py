"""lmdb_dao module.

This module provides the `LMDBDAO` class for interacting with an LMDB-backed database.
"""

from time import time
from typing import List, Dict

import lmdb
import json
import pandas as pd

from flowcept import WorkflowObject, AgentObject
from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import PERF_LOG, LMDB_SETTINGS
from flowcept.flowceptor.consumers.consumer_utils import curate_dict_task_messages


class LMDBDAO(DocumentDBDAO):
    """DocumentDBDAO implementation for interacting with LMDB.

    Provides methods for storing and retrieving task and workflow data.
    """

    _shared_handles = {}

    def __init__(self):
        # Avoid reopening LMDB for every DAO instance: lmdb can reject
        # opening the same environment path more than once per process.
        self._initialized = False
        self._path = None
        self._open()
        self._initialized = True
        self.logger = FlowceptLogger()

    def _open(self):
        """Open LMDB environment and databases."""
        path = LMDB_SETTINGS.get("path", "flowcept_lmdb")
        handle = LMDBDAO._shared_handles.get(path)
        if handle is None:
            env = lmdb.open(path, map_size=10**12, max_dbs=5)
            handle = {
                "env": env,
                "tasks_db": env.open_db(b"tasks"),
                "workflows_db": env.open_db(b"workflows"),
                "agents_db": env.open_db(b"agents"),
                "dashboards_db": env.open_db(b"dashboards"),
                "ref_count": 0,
            }
            LMDBDAO._shared_handles[path] = handle

        handle["ref_count"] += 1
        self._path = path
        self._env = handle["env"]
        self._tasks_db = handle["tasks_db"]
        self._workflows_db = handle["workflows_db"]
        self._agents_db = handle["agents_db"]
        self._dashboards_db = handle["dashboards_db"]
        self._initialized = True
        self._is_closed = False

    def insert_and_update_many_tasks(self, docs: List[Dict], indexing_key=None):
        """Insert or update multiple task documents in the LMDB database.

        Parameters
        ----------
        docs : list of dict
            A list of task documents to insert or update.
        indexing_key : str, optional
            Key used for indexing task messages.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            t0 = 0
            if PERF_LOG:
                t0 = time()
            indexed_buffer = curate_dict_task_messages(
                docs, indexing_key, t0, convert_times=False, keys_to_drop=["data"]
            )

            with self._env.begin(write=True, db=self._tasks_db) as txn:
                for key, value in indexed_buffer.items():
                    k, v = key.encode(), json.dumps(value).encode()
                    txn.put(k, v)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_one_task(self, task_dict):
        """Insert a single task document.

        Parameters
        ----------
        task_dict : dict
            The task document to insert.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            with self._env.begin(write=True, db=self._tasks_db) as txn:
                k, v = task_dict.get("task_id").encode(), json.dumps(task_dict).encode()
                txn.put(k, v)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_or_update_workflow(self, wf_obj: WorkflowObject):
        """Insert or update a workflow document.

        Parameters
        ----------
        wf_obj : WorkflowObject
            Workflow object to insert or update.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            _dict = wf_obj.to_dict()
            with self._env.begin(write=True, db=self._workflows_db) as txn:
                key = _dict.get("workflow_id").encode()
                value = json.dumps(_dict).encode()
                txn.put(key, value)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def save_workflow_domain_data_schema(self, workflow_id: str, fields: Dict):
        """Update selected workflow fields without replacing the full document."""
        try:
            with self._env.begin(write=True, db=self._workflows_db) as txn:
                key = workflow_id.encode()
                existing = txn.get(key)
                doc = json.loads(existing.decode()) if existing else {"workflow_id": workflow_id, "type": "workflow"}
                doc.update(fields)
                txn.put(key, json.dumps(doc).encode())
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def insert_or_update_agent(self, agent_obj: AgentObject):
        """Insert or update an agent document.

        Parameters
        ----------
        agent_obj : AgentObject
            Agent object to insert or update.

        Returns
        -------
        bool
            True if the operation succeeds, False otherwise.
        """
        try:
            _dict = agent_obj.to_dict()
            with self._env.begin(write=True, db=self._agents_db) as txn:
                key = _dict.get("agent_id").encode()
                value = json.dumps(_dict).encode()
                txn.put(key, value)
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def liveness_test(self) -> bool:
        """Return True when LMDB is enabled and the environment is open."""
        from flowcept.configs import LMDB_ENABLED

        if not LMDB_ENABLED:
            self.logger.warning("LMDB liveness check: LMDB_ENABLED is False — store is disabled.")
            return False
        try:
            with self._env.begin():
                pass
            return True
        except Exception as e:
            self.logger.error(f"LMDB liveness check failed: {e}")
            return False

    def delete_task_keys(self, key_name, keys_list: List[str]) -> bool:
        """Delete task documents by a key value list.

        When deleting by task_id, deletes keys directly. Otherwise, scans
        tasks and deletes matching entries.
        """
        if self._is_closed:
            self._open()
        if type(keys_list) is not list:
            keys_list = [keys_list]
        try:
            with self._env.begin(write=True, db=self._tasks_db) as txn:
                if key_name == "task_id":
                    for key in keys_list:
                        if key is None:
                            continue
                        txn.delete(str(key).encode())
                else:
                    cursor = txn.cursor()
                    for key, value in cursor:
                        entry = json.loads(value.decode())
                        if entry.get(key_name) in keys_list:
                            cursor.delete()
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def delete_agents_with_filter(self, filter) -> bool:
        """Delete agent documents that match the specified filter."""
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(write=True, db=self._agents_db) as txn:
                cursor = txn.cursor()
                for key, value in cursor:
                    entry = json.loads(value.decode())
                    if LMDBDAO._match_filter(entry, filter):
                        cursor.delete()
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def count_tasks(self) -> int:
        """Count number of docs in tasks collection."""
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(db=self._tasks_db) as txn:
                return txn.stat().get("entries", 0)
        except Exception as e:
            self.logger.exception(e)
            return -1

    def count_workflows(self) -> int:
        """Count number of docs in workflows collection."""
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(db=self._workflows_db) as txn:
                return txn.stat().get("entries", 0)
        except Exception as e:
            self.logger.exception(e)
            return -1

    @staticmethod
    def _match_filter(entry, filter):
        """Check if an entry matches a Mongo-style filter dict.

        Supports: ``$and``, ``$or``, ``$eq``, ``$ne``, ``$gt``, ``$gte``,
        ``$lt``, ``$lte``, ``$in``, ``$nin``, and plain equality.
        """
        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import ALLOWED_FILTER_OPERATORS

        _field_ops = {
            "$eq": lambda v, o: v == o,
            "$ne": lambda v, o: v != o,
            "$gt": lambda v, o: v is not None and v > o,
            "$gte": lambda v, o: v is not None and v >= o,
            "$lt": lambda v, o: v is not None and v < o,
            "$lte": lambda v, o: v is not None and v <= o,
            "$in": lambda v, o: v in o,
            "$nin": lambda v, o: v not in o,
        }

        if not filter:
            return True

        for key, value in filter.items():
            if key == "$or":
                if not any(LMDBDAO._match_filter(entry, clause) for clause in value):
                    return False
            elif key == "$and":
                if not all(LMDBDAO._match_filter(entry, clause) for clause in value):
                    return False
            elif key.startswith("$"):
                if key not in ALLOWED_FILTER_OPERATORS:
                    raise ValueError(f"Unsupported filter operator: {key}")
            elif isinstance(value, dict):
                entry_val = entry.get(key)
                for op, op_val in value.items():
                    fn = _field_ops.get(op)
                    if fn is None or not fn(entry_val, op_val):
                        return False
            else:
                if entry.get(key) != value:
                    return False
        return True

    def to_df(self, collection="tasks", filter=None) -> pd.DataFrame:
        """Fetch data from LMDB and return a DataFrame with optional MongoDB-style filtering.

        Args:
            collection (str, optional): Collection name. Should be tasks or workflows
            filter (dict, optional): A dictionary representing the filter criteria.
                 Example: {"workflow_id": "123", "status": "completed"}

        Returns
        -------
         pd.DataFrame: A DataFrame containing the filtered data.
        """
        docs = self.query(collection=collection, filter=filter)
        return pd.DataFrame(docs)

    def query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
        collection="tasks",
    ) -> List[Dict]:
        """Query data from LMDB.

        Parameters
        ----------
        filter : dict, optional
            Filter criteria.
        projection : dict, optional
            Fields to include or exclude.
        limit : int, optional
            Maximum number of results to return.
        sort : list, optional
            Sorting criteria.
        aggregation : list, optional
            Aggregation stages.
        remove_json_unserializables : bool, optional
            Remove JSON-unserializable fields.
        collection : str, optional
            Name of the collection ('tasks' or 'workflows'). Default is 'tasks'.

        Returns
        -------
        list of dict
            A list of queried documents.
        """
        if self._is_closed:
            self._open()

        if collection == "tasks":
            _db = self._tasks_db
        elif collection == "workflows":
            _db = self._workflows_db
        elif collection == "agents":
            _db = self._agents_db
        else:
            self.logger.warning(f"LMDB does not support collection '{collection}'. Returning None.")
            return None

        try:
            data = []
            with self._env.begin(db=_db) as txn:
                cursor = txn.cursor()
                for key, value in cursor:
                    entry = json.loads(value.decode())
                    if LMDBDAO._match_filter(entry, filter):
                        data.append(entry)
            return data
        except Exception as e:
            self.logger.exception(e)
            return None

    def task_query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
    ):
        """Query tasks collection in the LMDB database.

        Parameters
        ----------
        filter : dict, optional
            Filter criteria for the query.
        projection : dict, optional
            Fields to include or exclude in the results.
        limit : int, optional
            Maximum number of results to return.
        sort : list of tuple, optional
            Sorting criteria. Example: [("field", "asc"), ("field", "desc")].
        aggregation : list, optional
            Aggregation pipeline stages for advanced queries.
        remove_json_unserializables : bool, optional
            Remove JSON-unserializable fields from the results.

        Returns
        -------
        list of dict
            A list of task documents that match the query criteria.
        """
        return self.query(
            collection="tasks",
            filter=filter,
            projection=projection,
            limit=limit,
            sort=sort,
            aggregation=aggregation,
            remove_json_unserializables=remove_json_unserializables,
        )

    def workflow_query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
    ):
        """Query workflows collection in the LMDB database.

        Parameters
        ----------
        filter : dict, optional
            Filter criteria for the query.
        projection : dict, optional
            Fields to include or exclude in the results.
        limit : int, optional
            Maximum number of results to return.
        sort : list of tuple, optional
            Sorting criteria. Example: [("field", "asc"), ("field", "desc")].
        aggregation : list, optional
            Aggregation pipeline stages for advanced queries.
        remove_json_unserializables : bool, optional
            Remove JSON-unserializable fields from the results.

        Returns
        -------
        list of dict
            A list of workflow documents that match the query criteria.
        """
        return self.query(
            collection="workflows",
            filter=filter,
            projection=projection,
            limit=limit,
            sort=sort,
            aggregation=aggregation,
            remove_json_unserializables=remove_json_unserializables,
        )

    def agent_query(
        self,
        filter=None,
        projection=None,
        limit=None,
        sort=None,
        aggregation=None,
        remove_json_unserializables=None,
    ):
        """Query agents collection in the LMDB database."""
        return self.query(
            collection="agents",
            filter=filter,
            projection=projection,
            limit=limit,
            sort=sort,
            aggregation=aggregation,
            remove_json_unserializables=remove_json_unserializables,
        )

    def save_dashboard(self, dashboard: Dict) -> bool:
        """Insert or replace a dashboard document.

        Parameters
        ----------
        dashboard : dict
            Dashboard document; must contain ``dashboard_id``.

        Returns
        -------
        bool
            True on success.
        """
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(write=True, db=self._dashboards_db) as txn:
                key = dashboard["dashboard_id"].encode()
                txn.put(key, json.dumps(dashboard).encode())
            return True
        except Exception as e:
            self.logger.exception(e)
            return False

    def get_dashboard(self, dashboard_id: str) -> Dict:
        """Get a dashboard document by id.

        Parameters
        ----------
        dashboard_id : str
            Dashboard identifier.

        Returns
        -------
        dict or None
            The dashboard document, or None when not found.
        """
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(db=self._dashboards_db) as txn:
                value = txn.get(dashboard_id.encode())
                return json.loads(value.decode()) if value else None
        except Exception as e:
            self.logger.exception(e)
            return None

    def list_dashboards(self, filter: Dict = None) -> List[Dict]:
        """List dashboard documents, optionally filtered.

        Parameters
        ----------
        filter : dict, optional
            Key/value pairs to match against stored documents (equality only).

        Returns
        -------
        list of dict
            Matching dashboard documents.
        """
        if self._is_closed:
            self._open()
        try:
            results = []
            with self._env.begin(db=self._dashboards_db) as txn:
                cursor = txn.cursor()
                for _, value in cursor:
                    doc = json.loads(value.decode())
                    if filter is None or all(doc.get(k) == v for k, v in filter.items()):
                        results.append(doc)
            return results
        except Exception as e:
            self.logger.exception(e)
            return []

    def delete_dashboard(self, dashboard_id: str) -> bool:
        """Delete a dashboard document by id.

        Parameters
        ----------
        dashboard_id : str
            Dashboard identifier.

        Returns
        -------
        bool
            True when a document was deleted, False otherwise.
        """
        if self._is_closed:
            self._open()
        try:
            with self._env.begin(write=True, db=self._dashboards_db) as txn:
                return txn.delete(dashboard_id.encode())
        except Exception as e:
            self.logger.exception(e)
            return False

    def task_summary(self, filter: Dict) -> Dict:
        """Summarize tasks via in-process aggregation (LMDB path).

        Returns status counts, per-activity stats, and time range for tasks matching filter.
        """
        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import _merge_summary_rows, _duration

        docs = (
            self.task_query(
                filter=filter,
                projection=["activity_id", "status", "started_at", "ended_at"],
            )
            or []
        )
        groups: Dict = {}
        for doc in docs:
            key = (doc.get("activity_id"), doc.get("status"))
            group = groups.setdefault(
                key,
                {
                    "activity_id": key[0],
                    "status": key[1],
                    "count": 0,
                    "durations": [],
                    "min_started_at": None,
                    "max_ended_at": None,
                },
            )
            group["count"] += 1
            dur = _duration(doc)
            if dur is not None:
                group["durations"].append(dur)
            started, ended = doc.get("started_at"), doc.get("ended_at")
            if isinstance(started, (int, float)):
                current = group["min_started_at"]
                group["min_started_at"] = started if current is None else min(current, started)
            if isinstance(ended, (int, float)):
                current = group["max_ended_at"]
                group["max_ended_at"] = ended if current is None else max(current, ended)
        rows = []
        for group in groups.values():
            durations = group.pop("durations")
            group["avg_duration"] = sum(durations) / len(durations) if durations else None
            group["min_duration"] = min(durations) if durations else None
            group["max_duration"] = max(durations) if durations else None
            group["sum_duration"] = sum(durations) if durations else None
            rows.append(group)
        return _merge_summary_rows(rows)

    def derive_campaigns(self, campaign_id: str = None) -> List[Dict]:
        """Derive campaign summaries via in-process aggregation (LMDB path)."""
        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import to_epoch

        campaigns: Dict = {}

        def _campaign(cid):
            return campaigns.setdefault(
                cid,
                {
                    "campaign_id": cid,
                    "workflow_count": 0,
                    "task_count": 0,
                    "users": set(),
                    "workflow_names": set(),
                    "first_ts": None,
                    "last_ts": None,
                },
            )

        def _expand(record, *values):
            for raw in values:
                val = to_epoch(raw)
                if val is None:
                    continue
                record["first_ts"] = val if record["first_ts"] is None else min(record["first_ts"], val)
                record["last_ts"] = val if record["last_ts"] is None else max(record["last_ts"], val)

        wf_filter = {"campaign_id": {"$exists": True, "$ne": None}}
        if campaign_id is not None:
            wf_filter["campaign_id"] = campaign_id
        for doc in self.workflow_query(filter=wf_filter) or []:
            if not doc.get("campaign_id"):
                continue
            record = _campaign(doc["campaign_id"])
            record["workflow_count"] += 1
            if doc.get("user"):
                record["users"].add(doc["user"])
            if doc.get("name"):
                record["workflow_names"].add(doc["name"])
            _expand(record, doc.get("utc_timestamp"))

        for doc in self.task_query(filter=wf_filter, projection=["campaign_id", "started_at", "ended_at"]) or []:
            if not doc.get("campaign_id"):
                continue
            record = _campaign(doc["campaign_id"])
            record["task_count"] += 1
            _expand(record, doc.get("started_at"), doc.get("ended_at"))

        results = []
        for record in campaigns.values():
            record["users"] = sorted(record["users"])
            record["workflow_names"] = sorted(record["workflow_names"])
            results.append(record)
        results.sort(
            key=lambda r: (1, r["last_ts"]) if r["last_ts"] is not None else (0, float("-inf")),
            reverse=True,
        )
        return results

    def derive_agents(self, filter: Dict = None) -> List[Dict]:
        """Derive agent summaries via in-process aggregation (LMDB path)."""

        def _ts(val):
            if val is None:
                return None
            if isinstance(val, (int, float)):
                return float(val)
            from datetime import datetime as _dt

            if isinstance(val, _dt):
                return val.timestamp()
            if isinstance(val, str):
                try:
                    return _dt.fromisoformat(val.replace("Z", "+00:00")).timestamp()
                except Exception:
                    return None
            return None

        try:
            stored = self.agent_query(filter=filter or {}) or []
        except Exception as e:
            self.logger.error(f"Error querying stored agents: {e}")
            stored = []
        stored = [a for a in stored if a.get("agent_id") not in ("train_agent_id", "orchestrator_agent_id")]
        if not stored:
            return []

        agent_ids = [a["agent_id"] for a in stored if "agent_id" in a]
        docs = (
            self.task_query(
                filter={"agent_id": {"$in": agent_ids}},
                projection=[
                    "agent_id",
                    "activity_id",
                    "source_agent_id",
                    "campaign_id",
                    "workflow_id",
                    "registered_at",
                ],
            )
            or []
        )

        stats_map: Dict = {}
        for doc in docs:
            agent_id = doc.get("agent_id")
            if not agent_id:
                continue
            record = stats_map.setdefault(
                agent_id,
                {
                    "task_count": 0,
                    "activities": set(),
                    "source_agent_ids": set(),
                    "campaign_ids": set(),
                    "workflow_ids": set(),
                    "last_active": None,
                },
            )
            record["task_count"] += 1
            for key, field in (
                ("activities", "activity_id"),
                ("source_agent_ids", "source_agent_id"),
                ("campaign_ids", "campaign_id"),
                ("workflow_ids", "workflow_id"),
            ):
                if doc.get(field):
                    record[key].add(doc[field])
            ts = _ts(doc.get("registered_at"))
            if ts is not None:
                current = record["last_active"]
                record["last_active"] = ts if current is None else max(current, ts)
        for record in stats_map.values():
            for key in ("activities", "source_agent_ids", "campaign_ids", "workflow_ids"):
                record[key] = sorted(record[key])

        agents = []
        for sa in stored:
            agent_id = sa["agent_id"]
            stat = stats_map.get(
                agent_id,
                {
                    "task_count": 0,
                    "activities": [],
                    "source_agent_ids": [],
                    "campaign_ids": [],
                    "workflow_ids": [],
                    "last_active": None,
                },
            )
            if stat["task_count"] == 0:
                continue
            agents.append(
                {
                    "agent_id": agent_id,
                    "task_count": stat["task_count"],
                    "activities": stat["activities"],
                    "source_agent_ids": stat["source_agent_ids"],
                    "campaign_ids": stat["campaign_ids"],
                    "workflow_ids": stat["workflow_ids"],
                    "last_active": stat["last_active"],
                    "name": sa.get("name"),
                    "workflow_id": sa.get("workflow_id"),
                    "registered_at": _ts(sa.get("registered_at")),
                }
            )
        agents.sort(
            key=lambda a: (1, a["registered_at"]) if a["registered_at"] is not None else (0, float("-inf")),
            reverse=True,
        )
        return agents

    def telemetry_timeseries(
        self, filter: Dict, fields: List, x_field: str = "started_at", limit: int = 1000
    ) -> List[Dict]:
        """Extract plottable rows of dot-notated fields from tasks (LMDB path)."""
        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import get_nested

        top_level = sorted({f.split(".")[0] for f in fields} | {x_field.split(".")[0]})
        docs = (
            self.task_query(
                filter=filter,
                projection=["task_id", "activity_id"] + top_level,
                limit=limit,
            )
            or []
        )
        rows = []
        for doc in docs:
            row = {
                x_field: get_nested(doc, x_field),
                "task_id": doc.get("task_id"),
                "activity_id": doc.get("activity_id"),
            }  # noqa: E501
            row.update({f: get_nested(doc, f) for f in fields})
            rows.append(row)
        rows.sort(key=lambda r: (r[x_field] is None, r[x_field]))
        return rows

    def resolve_chart_data(self, data: Dict, context: Dict = None) -> Dict:
        """Resolve a declarative chart spec into plottable rows (LMDB path)."""
        from collections import defaultdict

        from flowcept.commons.daos.docdb_dao.docdb_dao_utils import (
            _merge_context_filter,
            _metric_key,
            get_nested,
            to_epoch,
        )

        card_filter = data.get("filter") or {}
        query_filter = _merge_context_filter(card_filter, context)
        source = data.get("source", "tasks")
        limit = data.get("limit") or 1000
        group_by = data.get("group_by")
        metrics = data.get("metrics") or []
        x_field = data.get("x")
        y_fields = data.get("y") or []

        if source == "collection_sizes":
            # LMDB has no bsonSize equivalent; return empty.
            return {"rows": [], "count": 0}

        if group_by or metrics:
            metrics = metrics or [{"field": "", "agg": "count"}]
            has_elapsed = any(m.get("field") == "elapsed" for m in metrics)
            fields = sorted({m["field"] for m in metrics if m.get("field") and m["field"] != "elapsed"})
            elapsed_fields = ["started_at", "ended_at"] if has_elapsed else []
            top_level = sorted(
                {f.split(".")[0] for f in fields}
                | ({group_by.split(".")[0]} if group_by else set())
                | set(elapsed_fields)
            )
            docs = self.query(collection=source, filter=query_filter, projection=top_level or None) or []
            grouped: Dict = defaultdict(list)
            for doc in docs:
                grouped[get_nested(doc, group_by) if group_by else None].append(doc)
            out = []
            for key, group_docs in grouped.items():
                record = {group_by or "group": key}
                for metric in metrics:
                    field = metric.get("field", "")
                    agg = metric.get("agg", "count")
                    if field == "elapsed":
                        values = []
                        for d in group_docs:
                            s, e = to_epoch(d.get("started_at")), to_epoch(d.get("ended_at"))
                            if s is not None and e is not None:
                                values.append(e - s)
                    else:
                        values = [v for v in (get_nested(d, field) for d in group_docs) if isinstance(v, (int, float))]
                    mk = _metric_key(metric)
                    if agg == "count":
                        record[mk] = len(group_docs)
                    elif not values:
                        record[mk] = None
                    elif agg == "avg":
                        record[mk] = sum(values) / len(values)
                    elif agg == "sum":
                        record[mk] = sum(values)
                    elif agg == "min":
                        record[mk] = min(values)
                    elif agg == "max":
                        record[mk] = max(values)
                out.append(record)
            out.sort(key=lambda r: str(r.get(group_by or "group")))
            rows = out[:limit]
            return {"rows": rows, "count": len(rows)}

        if x_field and y_fields:
            rows = self.telemetry_timeseries(query_filter, fields=y_fields, x_field=x_field, limit=limit)
            return {"rows": rows[:limit], "count": len(rows[:limit])}

        sort_raw = data.get("sort")
        sort = None if not sort_raw else [(s["field"], s["order"]) for s in sort_raw]
        rows = self.query(collection=source, filter=query_filter, limit=limit, sort=sort) or []
        rows = rows[:limit]
        return {"rows": rows, "count": len(rows)}

    def close(self):
        """Close lmdb."""
        if getattr(self, "_initialized"):
            super().close()
            setattr(self, "_initialized", False)
            path = self._path
            handle = LMDBDAO._shared_handles.get(path)
            if handle is not None:
                handle["ref_count"] -= 1
                if handle["ref_count"] <= 0:
                    handle["env"].close()
                    LMDBDAO._shared_handles.pop(path, None)
            self._is_closed = True

    def object_query(self, filter):
        """Query objects collection."""
        raise NotImplementedError

    def get_tasks_recursive(self, workflow_id, max_depth=999, mapping=None):
        """Get_tasks_recursive in LMDB."""
        raise NotImplementedError

    def dump_tasks_to_file_recursive(self, workflow_id, output_file="tasks.parquet", max_depth=999, mapping=None):
        """Dump_tasks_to_file_recursive in LMDB."""
        raise NotImplementedError

    def dump_to_file(self, collection, filter, output_file, export_format, should_zip):
        """Dump collection data to a CSV or Parquet file, optionally zipped."""
        import os
        import zipfile
        from datetime import datetime

        df = self.to_df(collection, filter)

        if output_file is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"{collection}_{ts}.{export_format}"

        if export_format == "csv":
            df.to_csv(output_file, index=False)
        elif export_format == "parquet":
            df.to_parquet(output_file, index=False)
        else:
            raise ValueError(f"Unsupported format '{export_format}'. Use 'csv' or 'parquet'.")

        if should_zip:
            zip_path = output_file + ".zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(output_file, arcname=os.path.basename(output_file))
            os.remove(output_file)

    def save_or_update_object(
        self,
        blob_obj,
        object,
        save_data_in_collection=False,
        pickle_=False,
        control_version=False,
    ):
        """Save object."""
        raise NotImplementedError

    def update_object_metadata(
        self,
        object_id,
        custom_metadata=None,
        tags=None,
        object_type=None,
        task_id=None,
        workflow_id=None,
        control_version=True,
    ):
        """Update object metadata only."""
        raise NotImplementedError

    def get_file_data(self, file_id):
        """Get file data."""
        raise NotImplementedError
