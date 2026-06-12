"""Derive a W3C-PROV-style dataflow graph from tasks' ``used``/``generated`` fields.

Node kinds follow PROV semantics: ``task`` nodes are PROV Activities and chunk
nodes are PROV Entities. Each task's ``used`` dict is packed into one "inputs"
chunk entity and its ``generated`` dict into one "outputs" chunk entity.
Chunks are deduplicated by content, so an output chunk identical to another
task's input chunk becomes a single shared node (direct lineage). Dashed
"derived" edges link a producer's output chunk to a consumer's input chunk
when they share non-trivial (key, value) pairs in temporal order.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.services.stats import _to_epoch

MAX_NODES = 400
_TASK_PROJECTION = [
    "task_id",
    "activity_id",
    "used",
    "generated",
    "started_at",
    "ended_at",
    "status",
    "agent_id",
    "source_agent_id",
]


def _is_trivial(value: Any) -> bool:
    """Values too common to imply a real producer→consumer link."""
    if value is None or isinstance(value, bool):
        return True
    if isinstance(value, str) and len(value) <= 1:
        return True
    if isinstance(value, (int, float)) and value in (0, 1, -1):
        return True
    return False


def _short(value: Any, max_len: int = 32) -> str:
    text = str(value)
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _signature(payload: Dict[str, Any]) -> str:
    """Stable content signature for a used/generated dict."""
    return json.dumps({k: repr(v) for k, v in sorted(payload.items())}, sort_keys=True)


def get_lineage_task_ids(db: DBAPI, workflow_id: str, seed_task_ids: List[str]) -> List[str]:
    """Return all task_ids reachable (ancestors + descendants) from the seed tasks.

    Traverses the provenance graph derived from tasks' ``used``/``generated``
    fields. If the workflow has no dataflow data, returns the seeds unchanged.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    workflow_id : str
        Workflow execution id — scopes the graph traversal.
    seed_task_ids : list of str
        Task IDs to start the traversal from.

    Returns
    -------
    list of str
        All task_ids in the lineage subgraph (includes seeds).
    """
    graph = build_dataflow(db, workflow_id)
    if not graph:
        return seed_task_ids

    fwd: Dict[str, List[str]] = {}
    bwd: Dict[str, List[str]] = {}
    for e in graph["edges"]:
        fwd.setdefault(e["source"], []).append(e["target"])
        bwd.setdefault(e["target"], []).append(e["source"])

    seeds: Set[str] = {f"task:{tid}" for tid in seed_task_ids}
    visited: Set[str] = set(seeds)
    stack = list(seeds)
    while stack:
        curr = stack.pop()
        for adj in fwd.get(curr, []) + bwd.get(curr, []):
            if adj not in visited:
                visited.add(adj)
                stack.append(adj)

    return [nid[5:] for nid in visited if nid.startswith("task:")]


def build_dataflow(db: DBAPI, workflow_id: str) -> Optional[Dict[str, Any]]:
    """Build the dataflow graph for a workflow.

    Parameters
    ----------
    db : DBAPI
        DB API facade.
    workflow_id : str
        Workflow execution id.

    Returns
    -------
    dict or None
        ``{"level", "nodes", "edges", "truncated"}`` or None when the workflow
        has no tasks with used/generated data.
    """
    tasks = db.task_query(filter={"workflow_id": workflow_id}, projection=_TASK_PROJECTION) or []
    tasks = [t for t in tasks if t.get("used") or t.get("generated")]
    if not tasks:
        return None
    tasks.sort(key=lambda t: _to_epoch(t.get("started_at")) or 0)
    return _coarse(tasks)


def _task_node(t: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": f"task:{t['task_id']}",
        "kind": "task",
        "label": t.get("activity_id") or "task",
        "stats": {
            "task_id": t["task_id"],
            "activity_id": t.get("activity_id"),
            "status": t.get("status"),
            "started_at": t.get("started_at"),
            "ended_at": t.get("ended_at"),
            "used": t.get("used") or {},
            "generated": t.get("generated") or {},
            "agent_id": t.get("agent_id"),
            "source_agent_id": t.get("source_agent_id"),
        },
    }


def _coarse(tasks: List[Dict[str, Any]]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    chunks: Dict[str, Dict[str, Any]] = {}  # signature -> chunk node
    truncated = False

    def _chunk(payload: Dict[str, Any], role: str) -> str:
        sig = _signature(payload)
        chunk = chunks.get(sig)
        if chunk is None:
            chunk = {
                "id": f"chunk:{len(chunks)}",
                "kind": "chunk",
                "label": f"{len(payload)} item{'s' if len(payload) != 1 else ''}",
                "stats": {"items": payload, "roles": set(), "generated_by": []},
            }
            chunks[sig] = chunk
        chunk["stats"]["roles"].add(role)
        return chunk["id"]

    # Producer index for derived chunk→chunk edges: (key, repr(value)) -> [(task, out_chunk_id)]
    producers: Dict[tuple, List[tuple]] = {}

    for t in tasks:
        if len(nodes) + len(chunks) > MAX_NODES:
            truncated = True
            break
        nodes.append(_task_node(t))
        tid = t["task_id"]
        used, generated = t.get("used") or {}, t.get("generated") or {}
        if used:
            in_id = _chunk(used, "input")
            edges.append({"source": in_id, "target": f"task:{tid}", "relation": "used"})
        if generated:
            out_id = _chunk(generated, "output")
            chunks[_signature(generated)]["stats"]["generated_by"].append(
                {
                    "activity": t.get("activity_id") or "task",
                    "task_id": tid,
                }
            )
            edges.append({"source": f"task:{tid}", "target": out_id, "relation": "generated"})
            for key, value in generated.items():
                if not _is_trivial(value):
                    producers.setdefault((key, repr(value)), []).append((t, out_id))

    # Derived edges: producer's output chunk → consumer's input chunk on shared values.
    seen_derived = set()
    for t in tasks:
        used = t.get("used") or {}
        if not used:
            continue
        in_id = _chunk(used, "input")
        t_start = _to_epoch(t.get("started_at"))
        for key, value in used.items():
            if _is_trivial(value):
                continue
            for producer, out_id in producers.get((key, repr(value)), ()):
                if producer["task_id"] == t["task_id"] or out_id == in_id:
                    continue
                p_end = _to_epoch(producer.get("ended_at"))
                if t_start is not None and p_end is not None and p_end > t_start:
                    continue
                if (out_id, in_id) not in seen_derived:
                    seen_derived.add((out_id, in_id))
                    edges.append({"source": out_id, "target": in_id, "relation": "derived"})

    for chunk in chunks.values():
        roles = chunk["stats"].pop("roles")
        role = "input/output" if len(roles) > 1 else next(iter(roles))
        chunk["stats"]["kind"] = role
        prefix = {"input": "inputs", "output": "outputs", "input/output": "data"}[role]
        chunk["label"] = f"{prefix} ({len(chunk['stats']['items'])})"
        nodes.append(chunk)

    return {"level": "coarse", "nodes": nodes, "edges": edges, "truncated": truncated}
