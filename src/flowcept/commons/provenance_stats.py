"""Aggregation and derivation services for webservice stats endpoints and dashboard cards.

Mongo-backed deployments use native aggregation pipelines; other backends (e.g., LMDB)
fall back to in-Python aggregation over plain queries.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from flowcept.commons.daos.docdb_dao.docdb_dao_base import DocumentDBDAO
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.commons.dashboard_schemas import ChartData, MetricSpec


def _to_epoch(value) -> Optional[float]:
    """Normalize a timestamp value (float epoch-sec, epoch-ms, ISO string, or datetime) to epoch seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Epoch milliseconds have 13 digits; epoch seconds have 10.
        return value / 1000.0 if value > 1e12 else float(value)
    if isinstance(value, str):
        from datetime import datetime, timezone

        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.replace(tzinfo=timezone.utc).timestamp() if dt.tzinfo is None else dt.timestamp()
        except ValueError:
            return None
    # pymongo returns datetime objects for BSON Date fields (e.g. from $min/$max aggregations)
    try:
        from datetime import datetime, timezone

        if isinstance(value, datetime):
            return value.replace(tzinfo=timezone.utc).timestamp() if value.tzinfo is None else value.timestamp()
    except Exception:
        pass
    return None


def _mongo_dao_or_none(db: Optional[DBAPI] = None) -> Optional[DocumentDBDAO]:
    """Return the DAO singleton when it supports raw aggregation pipelines, else None."""
    if db is not None and not isinstance(db, DBAPI):
        return None
    try:
        dao = DocumentDBDAO.get_instance(create_indices=False)
        return dao if hasattr(dao, "raw_pipeline") else None
    except Exception:
        return None


def get_nested(item: Dict[str, Any], field: str) -> Any:
    """Read a dot-notated field value from a document."""
    current = item
    for part in field.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _duration(doc: Dict[str, Any]) -> Optional[float]:
    started, ended = _to_epoch(doc.get("started_at")), _to_epoch(doc.get("ended_at"))
    if started is not None and ended is not None:
        return ended - started
    return None


def task_summary(db: DBAPI, filter: Dict[str, Any]) -> Dict[str, Any]:
    """Summarize tasks matching a filter: status counts, per-activity stats, and time range.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    filter : dict
        Mongo-style filter over the ``tasks`` collection.

    Returns
    -------
    dict
        ``{"count", "status_counts", "activity_stats", "time_range"}``.
    """
    dao = _mongo_dao_or_none(db)
    if dao is not None:
        return _task_summary_mongo(dao, filter)
    return _task_summary_python(db, filter)


def _task_summary_mongo(dao, filter: Dict[str, Any]) -> Dict[str, Any]:
    match = [{"$match": filter}] if filter else []
    rows = (
        dao.raw_pipeline(
            match
            + [
                {
                    "$group": {
                        "_id": {"activity_id": "$activity_id", "status": "$status"},
                        "count": {"$sum": 1},
                        "avg_duration": {"$avg": {"$subtract": ["$ended_at", "$started_at"]}},
                        "min_duration": {"$min": {"$subtract": ["$ended_at", "$started_at"]}},
                        "max_duration": {"$max": {"$subtract": ["$ended_at", "$started_at"]}},
                        "sum_duration": {"$sum": {"$subtract": ["$ended_at", "$started_at"]}},
                        "min_started_at": {"$min": "$started_at"},
                        "max_ended_at": {"$max": "$ended_at"},
                    }
                }
            ],
            collection="tasks",
        )
        or []
    )
    return _merge_summary_rows(
        [
            {
                "activity_id": row["_id"].get("activity_id"),
                "status": row["_id"].get("status"),
                **{k: row.get(k) for k in row if k != "_id"},
            }
            for row in rows
        ]
    )


def _task_summary_python(db: DBAPI, filter: Dict[str, Any]) -> Dict[str, Any]:
    docs = (
        db.task_query(
            filter=filter,
            projection=["activity_id", "status", "started_at", "ended_at"],
        )
        or []
    )
    groups: Dict[tuple, Dict[str, Any]] = {}
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
        duration = _duration(doc)
        if duration is not None:
            group["durations"].append(duration)
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


def _merge_summary_rows(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Combine per-(activity,status) rows into the summary response shape."""
    status_counts: Dict[str, int] = defaultdict(int)
    activities: Dict[str, Dict[str, Any]] = {}
    total = 0
    min_started, max_ended = None, None
    for row in rows:
        count = row.get("count") or 0
        total += count
        status = row.get("status") or "UNKNOWN"
        status_counts[status] += count

        activity = activities.setdefault(
            str(row.get("activity_id")),
            {
                "activity_id": row.get("activity_id"),
                "count": 0,
                "status_counts": defaultdict(int),
                "avg_duration": None,
                "min_duration": None,
                "max_duration": None,
                "sum_duration": None,
                "_weighted_sum": 0.0,
                "_weighted_count": 0,
            },
        )
        activity["count"] += count
        activity["status_counts"][status] += count
        for bound, op in (("min_duration", min), ("max_duration", max)):
            if row.get(bound) is not None:
                current = activity[bound]
                activity[bound] = row[bound] if current is None else op(current, row[bound])
        if row.get("sum_duration") is not None:
            activity["sum_duration"] = (activity["sum_duration"] or 0) + row["sum_duration"]
        if row.get("avg_duration") is not None:
            activity["_weighted_sum"] += row["avg_duration"] * count
            activity["_weighted_count"] += count

        if row.get("min_started_at") is not None:
            val = _to_epoch(row["min_started_at"])
            min_started = val if min_started is None else min(min_started, val)
        if row.get("max_ended_at") is not None:
            val = _to_epoch(row["max_ended_at"])
            max_ended = val if max_ended is None else max(max_ended, val)

    activity_stats = []
    for activity in activities.values():
        if activity.pop("_weighted_count"):
            activity["avg_duration"] = activity.pop("_weighted_sum") / activity["count"]
        else:
            activity.pop("_weighted_sum")
        activity["status_counts"] = dict(activity["status_counts"])
        activity_stats.append(activity)
    activity_stats.sort(key=lambda a: str(a["activity_id"]))

    return {
        "count": total,
        "status_counts": dict(status_counts),
        "activity_stats": activity_stats,
        "time_range": {"min_started_at": min_started, "max_ended_at": max_ended},
    }


def derive_campaigns(db: DBAPI) -> List[Dict[str, Any]]:
    """Derive campaign summaries by grouping workflows and tasks by ``campaign_id``.

    There is no campaigns collection; campaigns exist as a grouping key.

    Returns
    -------
    list of dict
        One record per campaign with workflow/task counts, users, names, and time range.
    """
    campaigns: Dict[str, Dict[str, Any]] = {}

    def _campaign(campaign_id: str) -> Dict[str, Any]:
        return campaigns.setdefault(
            campaign_id,
            {
                "campaign_id": campaign_id,
                "workflow_count": 0,
                "task_count": 0,
                "users": set(),
                "workflow_names": set(),
                "first_ts": None,
                "last_ts": None,
            },
        )

    def _expand_range(record: Dict[str, Any], *values) -> None:
        for raw in values:
            value = _to_epoch(raw)
            if value is None:
                continue
            record["first_ts"] = value if record["first_ts"] is None else min(record["first_ts"], value)
            record["last_ts"] = value if record["last_ts"] is None else max(record["last_ts"], value)

    dao = _mongo_dao_or_none(db)
    if dao is not None:
        wf_rows = (
            dao.raw_pipeline(
                [
                    {"$match": {"campaign_id": {"$exists": True, "$ne": None}}},
                    {
                        "$group": {
                            "_id": "$campaign_id",
                            "workflow_count": {"$sum": 1},
                            "users": {"$addToSet": "$user"},
                            "workflow_names": {"$addToSet": "$name"},
                            "first_ts": {"$min": "$utc_timestamp"},
                            "last_ts": {"$max": "$utc_timestamp"},
                        }
                    },
                ],
                collection="workflows",
            )
            or []
        )
        task_rows = (
            dao.raw_pipeline(
                [
                    {"$match": {"campaign_id": {"$exists": True, "$ne": None}}},
                    {
                        "$group": {
                            "_id": "$campaign_id",
                            "task_count": {"$sum": 1},
                            "first_ts": {"$min": "$started_at"},
                            "last_ts": {"$max": "$ended_at"},
                        }
                    },
                ],
                collection="tasks",
            )
            or []
        )
        for row in wf_rows:
            record = _campaign(row["_id"])
            record["workflow_count"] = row.get("workflow_count", 0)
            record["users"].update(u for u in row.get("users", []) if u)
            record["workflow_names"].update(n for n in row.get("workflow_names", []) if n)
            _expand_range(record, row.get("first_ts"), row.get("last_ts"))
        for row in task_rows:
            record = _campaign(row["_id"])
            record["task_count"] = row.get("task_count", 0)
            _expand_range(record, row.get("first_ts"), row.get("last_ts"))
    else:
        wf_filter = {"campaign_id": {"$exists": True, "$ne": None}}
        for doc in db.workflow_query(filter=wf_filter) or []:
            if not doc.get("campaign_id"):
                continue
            record = _campaign(doc["campaign_id"])
            record["workflow_count"] += 1
            if doc.get("user"):
                record["users"].add(doc["user"])
            if doc.get("name"):
                record["workflow_names"].add(doc["name"])
            _expand_range(record, doc.get("utc_timestamp"))
        task_docs = (
            db.task_query(
                filter=wf_filter,
                projection=["campaign_id", "started_at", "ended_at"],
            )
            or []
        )
        for doc in task_docs:
            if not doc.get("campaign_id"):
                continue
            record = _campaign(doc["campaign_id"])
            record["task_count"] += 1
            _expand_range(record, doc.get("started_at"), doc.get("ended_at"))

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


def derive_agents(db: DBAPI, filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """Derive agent summaries by grouping tasks by ``agent_id`` for agents in the agents collection.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    filter : dict, optional
        Extra Mongo-style filter for querying the agents collection.

    Returns
    -------
    list of dict
        One record per agent with task counts, activities, and last activity time.
    """

    def to_float_ts(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return float(val)
        from datetime import datetime as dt

        if isinstance(val, dt):
            return val.timestamp()
        if isinstance(val, str):
            try:
                return dt.fromisoformat(val.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None
        return None

    try:
        stored_agents = db.agent_query(filter=filter or {}) or []
    except Exception as e:
        from flowcept.commons.flowcept_logger import FlowceptLogger

        FlowceptLogger().error(f"Error querying stored agents: {e}")
        stored_agents = []

    # Filter out train_agent_id and orchestrator_agent_id
    stored_agents = [a for a in stored_agents if a.get("agent_id") not in ("train_agent_id", "orchestrator_agent_id")]

    if not stored_agents:
        return []

    agent_ids = [a["agent_id"] for a in stored_agents if "agent_id" in a]
    query_filter = {"agent_id": {"$in": agent_ids}}

    dao = _mongo_dao_or_none(db)
    if dao is not None:
        rows = (
            dao.raw_pipeline(
                [
                    {"$match": query_filter},
                    {
                        "$group": {
                            "_id": "$agent_id",
                            "task_count": {"$sum": 1},
                            "activities": {"$addToSet": "$activity_id"},
                            "source_agent_ids": {"$addToSet": "$source_agent_id"},
                            "campaign_ids": {"$addToSet": "$campaign_id"},
                            "workflow_ids": {"$addToSet": "$workflow_id"},
                            "last_active": {"$max": "$registered_at"},
                        }
                    },
                ],
                collection="tasks",
            )
            or []
        )
        stats_map = {
            row["_id"]: {
                "task_count": row.get("task_count", 0),
                "activities": sorted(a for a in row.get("activities", []) if a),
                "source_agent_ids": sorted(s for s in row.get("source_agent_ids", []) if s),
                "campaign_ids": sorted(c for c in row.get("campaign_ids", []) if c),
                "workflow_ids": sorted(w for w in row.get("workflow_ids", []) if w),
                "last_active": to_float_ts(row.get("last_active")),
            }
            for row in rows
        }
    else:
        docs = (
            db.task_query(
                filter=query_filter,
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
        stats_map = {}
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
            ts = to_float_ts(doc.get("registered_at"))
            if ts is not None:
                current = record["last_active"]
                record["last_active"] = ts if current is None else max(current, ts)
        for record in stats_map.values():
            for key in ("activities", "source_agent_ids", "campaign_ids", "workflow_ids"):
                record[key] = sorted(record[key])

    agents = []
    for sa in stored_agents:
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
                "registered_at": to_float_ts(sa.get("registered_at")),
            }
        )

    agents.sort(
        key=lambda a: (1, a["registered_at"]) if a["registered_at"] is not None else (0, float("-inf")),
        reverse=True,
    )
    return agents


def telemetry_timeseries(
    db: DBAPI,
    filter: Dict[str, Any],
    fields: List[str],
    x_field: str = "started_at",
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """Extract plottable rows of dot-notated (telemetry) fields from tasks.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    filter : dict
        Mongo-style filter over tasks.
    fields : list of str
        Dot-notated y-value paths (e.g., ``telemetry_at_end.cpu.percent_all``).
    x_field : str, optional
        X-axis field (a task time field by default).
    limit : int, optional
        Maximum number of rows.

    Returns
    -------
    list of dict
        Rows of ``{x_field, task_id, activity_id, <field>: value, ...}`` sorted by x.
    """
    top_level = sorted({field.split(".")[0] for field in fields} | {x_field.split(".")[0]})
    docs = (
        db.task_query(
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
        }
        row.update({field: get_nested(doc, field) for field in fields})
        rows.append(row)
    rows.sort(key=lambda r: (r[x_field] is None, r[x_field]))
    return rows


def _merge_context_filter(card_filter: Dict[str, Any], context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not context:
        return dict(card_filter)
    if not card_filter:
        return dict(context)
    return {"$and": [context, card_filter]}


def _resolve_collection_sizes(db: DBAPI, query_filter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return per-collection BSON byte totals for the given filter (e.g. workflow_id).

    Uses MongoDB ``$bsonSize`` on each of the three provenance collections.
    Returns an empty list when Mongo is unavailable.
    """
    dao = _mongo_dao_or_none(db)
    if dao is None:
        return []
    rows = []
    for collection in ("tasks", "objects", "workflows"):
        try:
            result = dao.raw_pipeline(
                [
                    {"$match": query_filter},
                    {"$group": {"_id": None, "bytes": {"$sum": {"$bsonSize": "$$ROOT"}}}},
                ],
                collection=collection,
            )
            bytes_val = result[0]["bytes"] if result else 0
        except Exception:
            bytes_val = 0
        rows.append({"collection": collection, "sum_bytes": bytes_val})
    return rows


def resolve_chart_data(db: DBAPI, data: "ChartData", context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Resolve a declarative card data binding into plottable rows.

    This is the single data contract shared by dashboard cards, the stats router,
    and LLM chart tools.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    data : ChartData
        Declarative binding (source, filter, group_by/metrics or x/y, sort, limit).
    context : dict, optional
        Dashboard-level filter ANDed into the card filter (e.g., ``{"campaign_id": ...}``).

    Returns
    -------
    dict
        ``{"rows": [...], "count": int}``.
    """
    query_filter = _merge_context_filter(data.filter, context)

    if data.source == "collection_sizes":
        rows = _resolve_collection_sizes(db, query_filter)
        return {"rows": rows, "count": len(rows)}

    if data.group_by or data.metrics:
        rows = _resolve_grouped(db, data, query_filter)
    elif data.x and data.y:
        rows = telemetry_timeseries(db, query_filter, fields=data.y, x_field=data.x, limit=data.limit)
    else:
        sort = None if data.sort is None else [(s.field, s.order) for s in data.sort]
        rows = (
            db.query(
                collection=data.source,
                filter=query_filter,
                limit=data.limit,
                sort=sort,
            )
            or []
        )
    rows = rows[: data.limit]
    return {"rows": rows, "count": len(rows)}


def _resolve_grouped(db: DBAPI, data: "ChartData", query_filter: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Group/aggregate rows for a card, using Mongo pipelines when available."""
    metrics = data.metrics or [MetricSpec(field="", agg="count")]
    dao = _mongo_dao_or_none(db)
    has_elapsed_metric = any(getattr(m, "field", None) == "elapsed" for m in metrics)
    if dao is not None and data.source in ("tasks", "workflows", "objects") and not has_elapsed_metric:
        group_id = f"${data.group_by}" if data.group_by else None
        group_stage: Dict[str, Any] = {"_id": group_id}
        # MongoDB forbids dots in $group output field names; use underscores internally
        # and remap back to the canonical key before returning.
        mongo_key_map: Dict[str, str] = {}
        for metric in metrics:
            canonical = _metric_key(metric)
            mongo_key = canonical.replace(".", "_")
            mongo_key_map[mongo_key] = canonical
            if metric.agg == "count":
                group_stage[mongo_key] = {"$sum": 1}
            else:
                group_stage[mongo_key] = {f"${metric.agg}": f"${metric.field}"}
        pipeline = ([{"$match": query_filter}] if query_filter else []) + [{"$group": group_stage}]
        rows = dao.raw_pipeline(pipeline, collection=data.source) or []
        out = []
        for row in rows:
            record = {data.group_by or "group": row.pop("_id")}
            for mongo_key, canonical in mongo_key_map.items():
                if mongo_key in row:
                    record[canonical] = row.pop(mongo_key)
            record.update(row)
            out.append(record)
        out.sort(key=lambda r: str(r.get(data.group_by or "group")))
        return out

    fields = sorted({m.field for m in metrics if m.field and m.field != "elapsed"})
    elapsed_fields = ["started_at", "ended_at"] if has_elapsed_metric else []
    top_level = sorted(
        {f.split(".")[0] for f in fields}
        | ({data.group_by.split(".")[0]} if data.group_by else set())
        | set(elapsed_fields)
    )
    docs = (
        db.query(
            collection=data.source,
            filter=query_filter,
            projection=top_level or None,
        )
        or []
    )
    grouped: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    for doc in docs:
        grouped[get_nested(doc, data.group_by) if data.group_by else None].append(doc)
    out = []
    for key, docs_in_group in grouped.items():
        record = {data.group_by or "group": key}
        for metric in metrics:
            if metric.field == "elapsed":
                # Compute elapsed as ended_at - started_at for each doc
                def _elapsed(d: Dict[str, Any]) -> Optional[float]:
                    s, e = _to_epoch(d.get("started_at")), _to_epoch(d.get("ended_at"))
                    return (e - s) if s is not None and e is not None else None

                values = [v for v in (_elapsed(d) for d in docs_in_group) if v is not None]
            else:
                values = [
                    v for v in (get_nested(d, metric.field) for d in docs_in_group) if isinstance(v, (int, float))
                ]
            if metric.agg == "count":
                record[_metric_key(metric)] = len(docs_in_group)
            elif not values:
                record[_metric_key(metric)] = None
            elif metric.agg == "avg":
                record[_metric_key(metric)] = sum(values) / len(values)
            elif metric.agg == "sum":
                record[_metric_key(metric)] = sum(values)
            elif metric.agg == "min":
                record[_metric_key(metric)] = min(values)
            elif metric.agg == "max":
                record[_metric_key(metric)] = max(values)
        out.append(record)
    out.sort(key=lambda r: str(r.get(data.group_by or "group")))
    return out


def _metric_key(metric: "MetricSpec") -> str:
    return f"{metric.agg}_{metric.field}" if metric.field else metric.agg
