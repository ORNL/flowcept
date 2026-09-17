# academy_coscientist/plugins/flowcept_langgraph_plugin.py
"""
FlowCept provenance plugin for LangGraph workflows.

Mirrors the design of FlowceptAcademyPlugin but targets LangGraph/LangChain
instead of Academy.  Provenance is captured through LangChain's standard
callback interface, which LangGraph respects for all graph, node, LLM, and
tool executions.

Provenance hierarchy produced:
  WorkflowObject  (one per graph.invoke / graph.ainvoke call)
    └─ TaskObject  subtype=langgraph_node      activity_id=<node_name>
         └─ TaskObject  subtype=llm_call       activity_id=<model_name>   (parent_task_id)
         └─ TaskObject  subtype=tool_call      activity_id=<tool_name>    (parent_task_id)

Key FlowCept fields:
  task_id          — uuid per event (generated here, not LangChain's run_id)
  workflow_id      — per graph-run sub-workflow id
  campaign_id      — from Flowcept.campaign_id
  parent_task_id   — links LLM/tool tasks to their enclosing node task
  group_id         — all tasks within one graph run share a group_id
  activity_id      — node name | model name | tool name
  subtype          — langgraph_node | llm_call | tool_call | langgraph_graph
  used / generated — inputs and outputs
  status           — FINISHED | ERROR (proper Status enum values)
  telemetry_at_start/end — CPU/memory snapshots via TelemetryCapture

Usage (three lines to wire up):

    from academy_coscientist.plugins.flowcept_langgraph_plugin import FlowceptLangGraphPlugin

    plugin = FlowceptLangGraphPlugin(config={"workflow_name": "my-graph"})
    plugin.start()
    result = graph.invoke(state, config={"callbacks": [plugin.callback_handler]})
    plugin.stop()

Or as a context manager:

    with FlowceptLangGraphPlugin(config={"workflow_name": "my-graph"}) as plugin:
        result = graph.invoke(state, config={"callbacks": [plugin.callback_handler]})
"""

from __future__ import annotations

import os
import threading
import time
import uuid
import logging
from contextlib import contextmanager
from typing import Any
from uuid import UUID

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provenance overhead timer (identical to flowcept_plugin.py)
# ---------------------------------------------------------------------------


class _ProvenanceStats:
    """Lightweight thread-safe accumulator for provenance capture timings."""

    __slots__ = ("_lock", "_counts", "_totals", "_mins", "_maxs", "_raw")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._totals: dict[str, float] = {}
        self._mins: dict[str, float] = {}
        self._maxs: dict[str, float] = {}
        self._raw: list[tuple[str, str, float]] = []

    def record(self, category: str, elapsed: float) -> None:
        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self._lock:
            if category not in self._counts:
                self._counts[category] = 0
                self._totals[category] = 0.0
                self._mins[category] = float("inf")
                self._maxs[category] = 0.0
            self._counts[category] += 1
            self._totals[category] += elapsed
            if elapsed < self._mins[category]:
                self._mins[category] = elapsed
            if elapsed > self._maxs[category]:
                self._maxs[category] = elapsed
            self._raw.append((ts, category, elapsed))

    def summary(self) -> str:
        col = 22
        header = f"{'Category':<{col}} {'N':>7} {'Total(ms)':>11} {'Mean(µs)':>9} {'Min(µs)':>8} {'Max(µs)':>8}"
        sep = "-" * len(header)
        rows = [header, sep]
        with self._lock:
            for cat in sorted(self._counts):
                n = self._counts[cat]
                total = self._totals[cat]
                mean = (total / n) if n else 0.0
                mn = self._mins.get(cat, 0.0)
                mx = self._maxs.get(cat, 0.0)
                rows.append(
                    f"{cat:<{col}} {n:>7} {total * 1e3:>11.3f} {mean * 1e6:>9.1f} {mn * 1e6:>8.1f} {mx * 1e6:>8.1f}"
                )
        return "\n".join(rows)

    def to_csv(self, path: str, workflow_id: str | None = None) -> None:
        import csv

        write_header = not os.path.exists(path)
        with self._lock:
            raw_snapshot = list(self._raw)
        wf = workflow_id or ""
        rows = [
            {
                "timestamp_utc": ts,
                "workflow_id": wf,
                "category": cat,
                "elapsed_us": round(elapsed * 1e6, 3),
            }
            for ts, cat, elapsed in raw_snapshot
        ]
        fieldnames = ["timestamp_utc", "workflow_id", "category", "elapsed_us"]
        with open(path, "a", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerows(rows)


# ---------------------------------------------------------------------------
# Interceptor wrapper (same pattern as AcademyInterceptor)
# ---------------------------------------------------------------------------


class LangGraphInterceptor:
    """Manages a BaseInterceptor directly for LangGraph provenance (Dask-style)."""

    def __init__(self) -> None:
        self._interceptor = None
        self._workflow_id: str | None = None
        self._campaign_id: str | None = None

    def start(self, workflow_name: str, campaign_id: str | None = None) -> None:
        """Start the interceptor and emit the top-level WorkflowObject."""
        from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        self._workflow_id = str(uuid.uuid4())
        self._campaign_id = campaign_id or str(uuid.uuid4())

        self._interceptor = BaseInterceptor(kind="langgraph")
        self._interceptor.start(
            bundle_exec_id=self._workflow_id,
            check_safe_stops=False,
        )

        wf = WorkflowObject()
        wf.workflow_id = self._workflow_id
        wf.campaign_id = self._campaign_id
        wf.name = workflow_name
        self._interceptor.send_workflow_message(wf)

    def stop(self) -> None:
        """Stop the interceptor, flushing any buffered provenance."""
        if self._interceptor is None:
            return
        try:
            self._interceptor.stop(check_safe_stops=False)
        except Exception as e:
            _log.warning("Interceptor stop error: %r", e)
        self._interceptor = None

    @property
    def telemetry_capture(self):
        """Return the interceptor's TelemetryCapture, or None when not started."""
        return self._interceptor.telemetry_capture if self._interceptor else None

    def send_graph_workflow(self, graph_name: str, group_id: str) -> str:
        """Emit a WorkflowObject for one graph invocation; return its workflow_id."""
        if self._interceptor is None:
            return str(uuid.uuid4())
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        wf = WorkflowObject()
        wf.workflow_id = str(uuid.uuid4())
        wf.name = graph_name
        wf.campaign_id = self._campaign_id
        wf.parent_workflow_id = self._workflow_id
        wf.custom_metadata = {"group_id": group_id, "graph_name": graph_name}
        self._interceptor.send_workflow_message(wf)
        return wf.workflow_id

    def intercept_task(self, task_dict: dict) -> None:
        """Enrich a task dict with ids and status, then send it to the interceptor."""
        if self._interceptor is None:
            return
        from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
        from flowcept.commons.vocabulary import Status

        task_dict.setdefault("task_id", str(uuid.uuid4()))
        task_dict.setdefault("workflow_id", self._workflow_id)
        task_dict.setdefault("campaign_id", self._campaign_id)

        raw = task_dict.get("status", "FINISHED")
        if isinstance(raw, str):
            try:
                task_dict["status"] = Status[raw].value
            except KeyError:
                task_dict["status"] = Status.FINISHED.value

        TaskObject.enrich_task_dict(task_dict)
        self._interceptor.intercept(task_dict)


# ---------------------------------------------------------------------------
# LangGraph callback handler
# ---------------------------------------------------------------------------


class FlowceptLangGraphCallback:
    """
    LangChain BaseCallbackHandler that records provenance to FlowCept.

    Pass an instance to ``graph.invoke`` / ``graph.ainvoke`` via the
    ``config={"callbacks": [...]}`` argument.

    This class deliberately avoids subclassing ``BaseCallbackHandler`` at
    module import time so LangGraph/LangChain are optional dependencies.
    The actual class is built lazily in ``_build_handler_class()`` and
    cached in ``_HANDLER_CLASS``.
    """

    def __init__(self, interceptor: LangGraphInterceptor, stats: _ProvenanceStats | None) -> None:
        self._interceptor = interceptor
        self._stats = stats
        # Maps LangChain run_id (UUID) → FlowCept task_id (str)
        self._run_to_task: dict[UUID, str] = {}
        # Maps LangChain run_id → start timestamp
        self._run_start: dict[UUID, float] = {}
        # Tracks telemetry snapshots at node start
        self._run_tel_start: dict[UUID, Any] = {}
        # Maps graph-level run_id → group_id (shared by all tasks in one graph invocation)
        self._graph_runs: dict[UUID, str] = {}
        # Maps any child run_id → enclosing graph-level run_id (for group_id lookup)
        self._run_to_graph_run: dict[UUID, UUID] = {}
        # Maps graph-level run_id → Academy agent ID that produced the input data.
        # Set when the LangGraph state contains "_source_agent_id".
        self._graph_source_agent: dict[UUID, str] = {}
        # Buffers the start-time task skeleton (used, custom_metadata, parent_task_id …)
        # so on_chain_end / on_llm_end can emit ONE complete record with both
        # used (inputs) and generated (outputs) — same pattern as the Academy plugin.
        self._run_start_task: dict[UUID, dict] = {}

    # --- helpers ---

    def _is_graph_run(
        self,
        serialized: dict | None,
        tags: list[str] | None,
        parent_run_id=None,
    ) -> bool:
        """Return True when the chain event represents a top-level LangGraph graph invocation.

        Primary signal: parent_run_id is None (no enclosing run → this IS the graph).
        Secondary signal: serialized id / tags for belt-and-suspenders detection.
        """
        if parent_run_id is None:
            return True
        id_parts = (serialized or {}).get("id", [])
        graph_classes = {
            "CompiledStateGraph",
            "CompiledGraph",
            "Pregel",
            "StateGraph",
            "MessageGraph",
        }
        return bool(graph_classes.intersection(id_parts) or any(t.startswith("__pregel_") for t in (tags or [])))

    def _node_name(self, serialized: dict | None, name: str | None) -> str:
        """Extract a human-readable node name."""
        if name:
            return name
        id_parts = (serialized or {}).get("id", [])
        return id_parts[-1] if id_parts else "unknown_node"

    def _model_name(self, serialized: dict | None) -> str:
        id_parts = (serialized or {}).get("id", [])
        kwargs = (serialized or {}).get("kwargs", {})
        return kwargs.get("model_name") or kwargs.get("model") or (id_parts[-1] if id_parts else "unknown_model")

    def _tel(self) -> Any:
        tc = self._interceptor.telemetry_capture
        return tc.capture() if tc else None

    def _record(self, category: str, elapsed: float) -> None:
        if self._stats is not None:
            self._stats.record(category, elapsed)

    def _task_id_for(self, run_id: UUID) -> str:
        if run_id not in self._run_to_task:
            self._run_to_task[run_id] = str(uuid.uuid4())
        return self._run_to_task[run_id]

    def _group_id_for(self, run_id: UUID) -> str | None:
        """Return the group_id for the graph invocation enclosing this run."""
        if run_id in self._graph_runs:
            return self._graph_runs[run_id]
        graph_run_id = self._run_to_graph_run.get(run_id)
        if graph_run_id is not None:
            return self._graph_runs.get(graph_run_id)
        return None

    # --- chain events (graph & node) ---

    def on_chain_start(
        self,
        serialized: dict | None,
        inputs: dict | None,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Buffer a task skeleton for a starting graph or node run."""
        t0 = time.perf_counter()
        self._run_start[run_id] = time.time()
        self._run_tel_start[run_id] = self._tel()
        task_id = self._task_id_for(run_id)
        serialized = serialized or {}
        inputs = inputs or {}

        if self._is_graph_run(serialized, tags, parent_run_id):
            # Top-level graph invocation → emit a sub-WorkflowObject for
            # hierarchy tracking, and record a group_id shared by all tasks
            # in this invocation.  Tasks use the global workflow_id (not the
            # sub-workflow id) so that campaign_id / workflow_id are uniform.
            group_id = str(uuid.uuid4())
            graph_name = name or self._node_name(serialized, name)
            self._interceptor.send_graph_workflow(graph_name, group_id)
            self._graph_runs[run_id] = group_id
            source_agent_id = inputs.get("_source_agent_id")
            if source_agent_id:
                self._graph_source_agent[run_id] = str(source_agent_id)

            custom: dict[str, Any] = {"tags": tags or [], "graph_name": graph_name}
            if source_agent_id:
                custom["source_agent_id"] = str(source_agent_id)
            # Buffer the skeleton — emitted as ONE complete record in on_chain_end
            self._run_start_task[run_id] = {
                "task_id": task_id,
                "subtype": "langgraph_graph",
                "activity_id": graph_name,
                "group_id": group_id,
                "started_at": self._run_start[run_id],
                "used": {"inputs": _safe_clip(inputs)},
                "custom_metadata": custom,
            }
        else:
            # Node or sub-chain execution.
            node = self._node_name(serialized, name)
            # Find the enclosing graph run for group_id and source_agent_id.
            graph_run_id = None
            if parent_run_id and parent_run_id in self._graph_runs:
                graph_run_id = parent_run_id
            elif parent_run_id:
                graph_run_id = self._run_to_graph_run.get(parent_run_id)
            group_id = self._graph_runs.get(graph_run_id) if graph_run_id else None
            source_agent_id = self._graph_source_agent.get(graph_run_id) if graph_run_id else None

            # Record child → graph mapping so on_llm_end / on_tool_end can find group_id
            if graph_run_id is not None:
                self._run_to_graph_run[run_id] = graph_run_id

            parent_task_id = self._run_to_task.get(parent_run_id) if parent_run_id else None
            custom = {"tags": tags or [], "node_name": node}
            if source_agent_id:
                custom["source_agent_id"] = source_agent_id
            # Buffer the skeleton — emitted as ONE complete record in on_chain_end
            skeleton: dict[str, Any] = {
                "task_id": task_id,
                "subtype": "langgraph_node",
                "activity_id": node,
                "group_id": group_id,
                "started_at": self._run_start[run_id],
                "used": {"inputs": _safe_clip(inputs)},
                "custom_metadata": custom,
            }
            if parent_task_id:
                skeleton["parent_task_id"] = parent_task_id
            self._run_start_task[run_id] = skeleton

        self._record("chain_start", time.perf_counter() - t0)

    def on_chain_end(
        self,
        outputs: dict,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit the completed graph or node task with outputs and telemetry."""
        t0 = time.perf_counter()
        self._run_start.pop(run_id, time.time())
        tel_start = self._run_tel_start.pop(run_id, None)
        tel_end = self._tel()
        self._run_to_task.pop(run_id, None)

        is_graph = run_id in self._graph_runs
        if is_graph:
            self._graph_runs.pop(run_id)
            self._graph_source_agent.pop(run_id, None)
        else:
            self._run_to_graph_run.pop(run_id, None)

        # Merge buffered start skeleton with completion data → ONE complete record
        task: dict[str, Any] = self._run_start_task.pop(run_id, {})
        task.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {"outputs": _safe_clip(outputs)},
            }
        )
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        if tel_end is not None:
            task["telemetry_at_end"] = _tel_to_dict(tel_end)

        self._interceptor.intercept_task(task)
        self._record("chain_end", time.perf_counter() - t0)

    def on_chain_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit the failed graph or node task with ERROR status."""
        t0 = time.perf_counter()
        self._run_start.pop(run_id, time.time())
        tel_start = self._run_tel_start.pop(run_id, None)
        self._run_to_task.pop(run_id, None)
        is_graph = run_id in self._graph_runs
        if is_graph:
            self._graph_runs.pop(run_id, None)
            self._graph_source_agent.pop(run_id, None)
        else:
            self._run_to_graph_run.pop(run_id, None)

        task: dict[str, Any] = self._run_start_task.pop(run_id, {})
        task.update(
            {
                "ended_at": time.time(),
                "status": "ERROR",
                "stderr": str(error),
            }
        )
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        self._interceptor.intercept_task(task)
        self._record("chain_error", time.perf_counter() - t0)

    # --- LLM events ---

    def on_llm_start(
        self,
        serialized: dict | None,
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Buffer an llm_call task skeleton for a starting LLM run."""
        t0 = time.perf_counter()
        self._run_start[run_id] = time.time()
        self._run_tel_start[run_id] = self._tel()
        task_id = self._task_id_for(run_id)
        # Propagate enclosing graph run mapping for group_id lookup in on_llm_end
        if parent_run_id is not None:
            graph_run_id = self._run_to_graph_run.get(parent_run_id) or (
                parent_run_id if parent_run_id in self._graph_runs else None
            )
            if graph_run_id is not None:
                self._run_to_graph_run[run_id] = graph_run_id
        group_id = self._group_id_for(run_id)
        parent_task_id = self._run_to_task.get(parent_run_id) if parent_run_id else None
        model_name = self._model_name(serialized)
        skeleton: dict[str, Any] = {
            "task_id": task_id,
            "subtype": "llm_call",
            "activity_id": model_name,
            "group_id": group_id,
            "started_at": self._run_start[run_id],
            "used": {"prompts": _safe_clip(prompts), "model": model_name},
            "custom_metadata": {"model": model_name},
        }
        if parent_task_id:
            skeleton["parent_task_id"] = parent_task_id
        self._run_start_task[run_id] = skeleton
        self._record("llm_start", time.perf_counter() - t0)

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit the completed llm_call task with response text and token usage."""
        t0 = time.perf_counter()
        self._run_start.pop(run_id, time.time())
        tel_start = self._run_tel_start.pop(run_id, None)
        tel_end = self._tel()
        self._run_to_task.pop(run_id, None)
        self._run_to_graph_run.pop(run_id, None)

        # Extract token usage and text from LangChain LLMResult
        usage: dict = {}
        text: str = ""
        model_name: str = "unknown"
        try:
            gen = response.generations
            if gen and gen[0]:
                text = gen[0][0].text if hasattr(gen[0][0], "text") else str(gen[0][0])
            llm_output = response.llm_output or {}
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            model_name = llm_output.get("model_name") or llm_output.get("model") or "unknown"
        except Exception:
            pass

        # Merge buffered start skeleton (includes prompts in used) with response data
        task: dict[str, Any] = self._run_start_task.pop(run_id, {})
        task.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {
                    "text": text,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                    "model": model_name,
                },
            }
        )
        # Update activity_id and model in custom_metadata if model is now known
        if model_name != "unknown":
            task["activity_id"] = model_name
            task.setdefault("custom_metadata", {})["model"] = model_name
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        if tel_end is not None:
            task["telemetry_at_end"] = _tel_to_dict(tel_end)

        self._interceptor.intercept_task(task)
        self._record("llm_end", time.perf_counter() - t0)

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit the failed llm_call task with ERROR status."""
        t0 = time.perf_counter()
        self._run_start.pop(run_id, None)
        tel_start = self._run_tel_start.pop(run_id, None)
        self._run_to_task.pop(run_id, None)
        self._run_to_graph_run.pop(run_id, None)

        task: dict[str, Any] = self._run_start_task.pop(run_id, {})
        task.update(
            {
                "ended_at": time.time(),
                "status": "ERROR",
                "stderr": str(error),
            }
        )
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        self._interceptor.intercept_task(task)
        self._record("llm_error", time.perf_counter() - t0)

    # --- Chat model events (same as LLM but different entry point) ---

    def on_chat_model_start(
        self,
        serialized: dict | None,
        messages: list,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Buffer an llm_call task skeleton for a starting chat-model run."""
        t0 = time.perf_counter()
        self._run_start[run_id] = time.time()
        self._run_tel_start[run_id] = self._tel()
        task_id = self._task_id_for(run_id)
        # Propagate enclosing graph run mapping for group_id lookup in on_llm_end
        if parent_run_id is not None:
            graph_run_id = self._run_to_graph_run.get(parent_run_id) or (
                parent_run_id if parent_run_id in self._graph_runs else None
            )
            if graph_run_id is not None:
                self._run_to_graph_run[run_id] = graph_run_id
        group_id = self._group_id_for(run_id)
        parent_task_id = self._run_to_task.get(parent_run_id) if parent_run_id else None
        model_name = self._model_name(serialized)
        # Serialize messages: each message is a list of BaseMessage objects
        serialized_messages = _safe_clip(
            [[m.content if hasattr(m, "content") else str(m) for m in turn] for turn in messages]
        )
        skeleton: dict[str, Any] = {
            "task_id": task_id,
            "subtype": "llm_call",
            "activity_id": model_name,
            "group_id": group_id,
            "started_at": self._run_start[run_id],
            "used": {"messages": serialized_messages, "model": model_name},
            "custom_metadata": {"model": model_name},
        }
        if parent_task_id:
            skeleton["parent_task_id"] = parent_task_id
        self._run_start_task[run_id] = skeleton
        self._record("chat_model_start", time.perf_counter() - t0)

    # on_chat_model_end fires on_llm_end in practice for most LangChain models

    # --- Tool events ---

    def on_tool_start(
        self,
        serialized: dict | None,
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Buffer a tool_call task skeleton for a starting tool run."""
        t0 = time.perf_counter()
        self._run_start[run_id] = time.time()
        self._run_tel_start[run_id] = self._tel()
        tool_name = (serialized or {}).get("name") or "unknown_tool"
        self._task_id_for(run_id)
        parent_task_id = self._run_to_task.get(parent_run_id) if parent_run_id else None
        # Propagate enclosing graph run mapping for group_id lookup in on_tool_end
        if parent_run_id is not None:
            graph_run_id = self._run_to_graph_run.get(parent_run_id) or (
                parent_run_id if parent_run_id in self._graph_runs else None
            )
            if graph_run_id is not None:
                self._run_to_graph_run[run_id] = graph_run_id
        group_id = self._group_id_for(run_id)
        task_id = self._run_to_task[run_id]
        # Buffer skeleton — emitted as ONE complete record in on_tool_end
        skeleton: dict[str, Any] = {
            "task_id": task_id,
            "subtype": "tool_call",
            "activity_id": tool_name,
            "group_id": group_id,
            "started_at": self._run_start[run_id],
            "used": {"input": _safe_clip(input_str)},
            "custom_metadata": {"tool_name": tool_name},
        }
        if parent_task_id:
            skeleton["parent_task_id"] = parent_task_id
        self._run_start_task[run_id] = skeleton
        self._record("tool_start", time.perf_counter() - t0)

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit the completed tool_call task with its output and telemetry."""
        t0 = time.perf_counter()
        tel_start = self._run_tel_start.pop(run_id, None)
        tel_end = self._tel()
        self._run_start.pop(run_id, None)
        self._run_to_task.pop(run_id, None)
        self._run_to_graph_run.pop(run_id, None)

        task: dict[str, Any] = self._run_start_task.pop(run_id, {})
        task.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {"output": _safe_clip(output)},
            }
        )
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        if tel_end is not None:
            task["telemetry_at_end"] = _tel_to_dict(tel_end)

        self._interceptor.intercept_task(task)
        self._record("tool_end", time.perf_counter() - t0)

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Emit the failed tool_call task with ERROR status."""
        t0 = time.perf_counter()
        tel_start = self._run_tel_start.pop(run_id, None)
        self._run_start.pop(run_id, None)
        self._run_to_task.pop(run_id, None)
        self._run_to_graph_run.pop(run_id, None)

        task: dict[str, Any] = self._run_start_task.pop(run_id, {})
        task.update(
            {
                "ended_at": time.time(),
                "status": "ERROR",
                "stderr": str(error),
            }
        )
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        self._interceptor.intercept_task(task)
        self._record("tool_error", time.perf_counter() - t0)


def _build_handler_class():
    """Lazily build a concrete BaseCallbackHandler subclass.

    Keeps LangChain/LangGraph imported only when the plugin is actually used.
    """
    from langchain_core.callbacks import BaseCallbackHandler

    class _ConcreteHandler(FlowceptLangGraphCallback, BaseCallbackHandler):
        """Concrete LangChain callback handler with FlowCept provenance."""

        def __init__(self, interceptor: LangGraphInterceptor, stats: _ProvenanceStats | None) -> None:
            # BaseCallbackHandler.__init__ must be called before our __init__
            # because it sets ignore_* flags that LangChain checks.
            BaseCallbackHandler.__init__(self)
            FlowceptLangGraphCallback.__init__(self, interceptor, stats)

        # Tell LangChain we handle all event types
        ignore_llm = False
        ignore_chain = False
        ignore_agent = False
        ignore_chat_model = False

    return _ConcreteHandler


_HANDLER_CLASS = None


# ---------------------------------------------------------------------------
# Module-level active interceptor — set by start() / from_academy_plugin()
# ---------------------------------------------------------------------------

_ACTIVE_INTERCEPTOR = None
_PROV_STATS: _ProvenanceStats | None = None


@contextmanager
def _timed(category: str):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        if _PROV_STATS is not None:
            _PROV_STATS.record(category, time.perf_counter() - t0)


def record_llm_call(payload: dict) -> None:
    """
    Public API to record an LLM call into the active FlowCept provenance graph.

    Converts the payload into a TaskObject (subtype=llm_call) and routes it
    through the active interceptor.  No-ops if the plugin has not been started.

    Minimum payload keys:
        type   : "chat_completion"
        model  : str
        text   : str
        usage  : dict with prompt_tokens / completion_tokens / total_tokens
    """
    interceptor = _ACTIVE_INTERCEPTOR
    if interceptor is None:
        return
    import uuid as _uuid

    with _timed("record_llm_call"):
        elapsed = payload.get("elapsed_s", 0.0)
        now = time.time()
        model = payload.get("model_used") or payload.get("model", "unknown")

        used: dict = {}
        for k in (
            "model",
            "model_used",
            "messages",
            "user_prompt",
            "system_prompt",
            "temperature",
            "top_p",
            "max_tokens",
            "reasoning_effort",
            "tools_provided",
            "tool_choice",
            "stop_sequences",
            "top_k",
            "thinking_budget_tokens",
        ):
            if k in payload:
                used[k] = payload[k]
        if payload.get("temperature_suppressed"):
            used["temperature_suppressed"] = True

        generated: dict = {}
        for k in (
            "text",
            "finish_reason",
            "stop_reason",
            "stop_sequence",
            "tool_calls",
            "tool_uses",
            "thinking_text",
            "system_fingerprint",
            "response_id",
            "usage",
            "elapsed_s",
        ):
            if k in payload:
                generated[k] = payload[k]
        if "error" in payload:
            generated["error"] = str(payload["error"])

        task: dict = {
            "task_id": str(_uuid.uuid4()),
            "subtype": "llm_call",
            "activity_id": model,
            "started_at": now - elapsed,
            "ended_at": now,
            "status": "ERROR" if "error" in payload else "FINISHED",
            "used": used,
            "generated": generated,
            "custom_metadata": {
                "model": model,
                "framework": payload.get("context", {}).get("framework", ""),
                "context": payload.get("context", {}),
            },
        }
        interceptor.intercept_task(task)


def openai_chat(
    prompt: str,
    model: str = "gpt-4o-mini",
    system: str = "You are a helpful assistant.",
    temperature: float | None = 0.3,
    top_p: float | None = None,
    max_tokens: int | None = None,
    n: int = 1,
    stop: list[str] | str | None = None,
    frequency_penalty: float = 0.0,
    presence_penalty: float = 0.0,
    seed: int | None = None,
    reasoning_effort: str | None = None,
    response_format: dict | None = None,
    tools: list | None = None,
    tool_choice: str | dict | None = None,
    user: str | None = None,
    context: dict | None = None,
) -> str:
    """
    Make an OpenAI chat completion call and record it for FlowCept provenance.

    Captures all request parameters and response fields as a child TaskObject.
    No-ops gracefully if OPENAI_API_KEY is not set or the plugin is not started.
    """
    import openai as _openai
    import os as _os
    import time as _time

    client = _openai.OpenAI(api_key=_os.environ.get("OPENAI_API_KEY"))
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]
    req: dict = {"model": model, "messages": messages, "n": n}
    if temperature is not None:
        req["temperature"] = temperature
    if top_p is not None:
        req["top_p"] = top_p
    if max_tokens is not None:
        req["max_completion_tokens"] = max_tokens
    if stop is not None:
        req["stop"] = stop
    if frequency_penalty != 0.0:
        req["frequency_penalty"] = frequency_penalty
    if presence_penalty != 0.0:
        req["presence_penalty"] = presence_penalty
    if seed is not None:
        req["seed"] = seed
    if reasoning_effort is not None:
        req["reasoning_effort"] = reasoning_effort
    if response_format is not None:
        req["response_format"] = response_format
    if tools is not None:
        req["tools"] = tools
    if tool_choice is not None:
        req["tool_choice"] = tool_choice
    if user is not None:
        req["user"] = user

    t0 = _time.time()
    response = client.chat.completions.create(**req)
    elapsed = _time.time() - t0

    choice = response.choices[0]
    text = choice.message.content or ""
    usage = response.usage or {}

    usage_dict: dict = {}
    for attr in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if hasattr(usage, attr):
            usage_dict[attr] = getattr(usage, attr)
    if hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
        ctd = usage.completion_tokens_details
        usage_dict["reasoning_tokens"] = getattr(ctd, "reasoning_tokens", None)
        usage_dict["accepted_prediction_tokens"] = getattr(ctd, "accepted_prediction_tokens", None)
        usage_dict["rejected_prediction_tokens"] = getattr(ctd, "rejected_prediction_tokens", None)
    if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
        ptd = usage.prompt_tokens_details
        usage_dict["cached_tokens"] = getattr(ptd, "cached_tokens", None)

    tool_calls = None
    if choice.message.tool_calls:
        tool_calls = [
            {
                "id": tc.id,
                "type": tc.type,
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in choice.message.tool_calls
        ]

    record_llm_call(
        {
            "type": "chat_completion",
            "model": model,
            "model_used": response.model,
            "messages": messages,
            "user_prompt": prompt,
            "system_prompt": system,
            "temperature": temperature,
            "temperature_suppressed": temperature is None,
            "top_p": top_p,
            "max_tokens": max_tokens,
            "n": n,
            "stop": stop,
            "frequency_penalty": frequency_penalty,
            "presence_penalty": presence_penalty,
            "seed": seed,
            "reasoning_effort": reasoning_effort,
            "response_format": response_format,
            "tools_provided": [t.get("function", {}).get("name") for t in (tools or [])],
            "tool_choice": tool_choice,
            "text": text,
            "finish_reason": choice.finish_reason,
            "tool_calls": tool_calls,
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "response_id": response.id,
            "created": response.created,
            "usage": usage_dict,
            "elapsed_s": elapsed,
            "context": context or {},
        }
    )
    return text


def anthropic_chat(
    prompt: str,
    model: str = "claude-haiku-4-5-20251001",
    system: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
    temperature: float | None = 1.0,
    top_p: float | None = None,
    top_k: int | None = None,
    stop_sequences: list[str] | None = None,
    tools: list | None = None,
    tool_choice: dict | None = None,
    thinking: dict | None = None,
    metadata: dict | None = None,
    context: dict | None = None,
) -> str:
    """
    Make an Anthropic (Claude) chat completion call and record it for FlowCept provenance.

    Captures all request/response fields — including thinking blocks, tool use,
    and cache token counts — as a child TaskObject.
    """
    import anthropic as _anthropic
    import os as _os
    import time as _time

    client = _anthropic.Anthropic(api_key=_os.environ.get("ANTHROPIC_API_KEY"))
    req: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    if temperature is not None:
        req["temperature"] = temperature
    if top_p is not None:
        req["top_p"] = top_p
    if top_k is not None:
        req["top_k"] = top_k
    if stop_sequences:
        req["stop_sequences"] = stop_sequences
    if tools:
        req["tools"] = tools
    if tool_choice:
        req["tool_choice"] = tool_choice
    if thinking:
        req["thinking"] = thinking
    if metadata:
        req["metadata"] = metadata

    t0 = _time.time()
    response = client.messages.create(**req)
    elapsed = _time.time() - t0

    text = ""
    thinking_text = ""
    tool_uses = []
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "thinking":
            thinking_text += getattr(block, "thinking", "")
        elif block.type == "tool_use":
            tool_uses.append({"id": block.id, "name": block.name, "input": block.input})

    usage = response.usage
    usage_dict = {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None),
    }

    record_llm_call(
        {
            "type": "chat_completion",
            "model": model,
            "model_used": response.model,
            "messages": req["messages"],
            "user_prompt": prompt,
            "system_prompt": system,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "temperature_suppressed": temperature is None,
            "top_p": top_p,
            "top_k": top_k,
            "stop_sequences": stop_sequences,
            "thinking_budget_tokens": (thinking or {}).get("budget_tokens"),
            "tools_provided": [t.get("name") for t in (tools or [])],
            "tool_choice": tool_choice,
            "text": text,
            "thinking_text": thinking_text if thinking_text else None,
            "finish_reason": response.stop_reason,
            "stop_sequence": response.stop_sequence,
            "tool_uses": tool_uses if tool_uses else None,
            "response_id": response.id,
            "usage": usage_dict,
            "elapsed_s": elapsed,
            "context": context or {},
        }
    )
    return text


# ---------------------------------------------------------------------------
# FlowceptAnthropicClient — wraps anthropic.Anthropic / AsyncAnthropic to
# capture full provenance for every messages.create / messages.stream call.
# ---------------------------------------------------------------------------


class FlowceptAnthropicClient:
    """Anthropic client wrapper that records every model call as FlowCept provenance.

    Wraps an ``anthropic.Anthropic`` (or ``AsyncAnthropic``) client and records
    every ``messages.create`` / ``messages.stream`` call as a FlowCept
    provenance record (subtype=llm_call) via ``record_llm_call()``.

    Usage::

        import anthropic
        from flowcept.agents.langgraph.langgraph_plugin import FlowceptAnthropicClient

        client = FlowceptAnthropicClient(anthropic.Anthropic(), agent_name="my-agent")
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            messages=[{"role": "user", "content": "Hello"}],
        )
    """

    def __init__(self, client, agent_name=None, context=None):
        self._inner = client
        self._agent_name = agent_name
        self._context: dict = context or {}
        self.messages = _FlowceptAnthropicMessages(client.messages, agent_name, self._context)

    def __getattr__(self, name):
        """Delegate every other attribute to the wrapped Anthropic client."""
        return getattr(self._inner, name)


class _FlowceptAnthropicMessages:
    def __init__(self, messages_resource, agent_name, context):
        self._inner = messages_resource
        self._agent_name = agent_name
        self._context = context

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def create(self, **kwargs):
        import time as _time

        t0 = _time.time()
        result = self._inner.create(**kwargs)
        self._record(kwargs, result, _time.time() - t0)
        return result

    async def async_create(self, **kwargs):
        import time as _time

        t0 = _time.time()
        result = await self._inner.create(**kwargs)
        self._record(kwargs, result, _time.time() - t0)
        return result

    def stream(self, **kwargs):
        import time as _time

        return _FlowceptAnthropicStream(self._inner.stream(**kwargs), kwargs, self._record, _time.time())

    def _record(self, kwargs, result, elapsed):
        try:
            model = kwargs.get("model", "unknown")
            text = ""
            thinking_text = ""
            tool_uses = []
            for block in getattr(result, "content", []):
                btype = getattr(block, "type", None)
                if btype == "text":
                    text += getattr(block, "text", "")
                elif btype == "thinking":
                    thinking_text += getattr(block, "thinking", "")
                elif btype == "tool_use":
                    tool_uses.append(
                        {
                            "id": getattr(block, "id", None),
                            "name": getattr(block, "name", None),
                            "input": getattr(block, "input", None),
                        }
                    )
            usage = getattr(result, "usage", None)
            usage_dict = (
                {
                    attr: getattr(usage, attr, None)
                    for attr in (
                        "input_tokens",
                        "output_tokens",
                        "cache_creation_input_tokens",
                        "cache_read_input_tokens",
                    )
                }
                if usage
                else {}
            )
            ctx = dict(self._context)
            if self._agent_name:
                ctx["agent_name"] = self._agent_name
            payload = {
                "type": "chat_completion",
                "model": model,
                "model_used": getattr(result, "model", model),
                "messages": kwargs.get("messages"),
                "system_prompt": kwargs.get("system"),
                "max_tokens": kwargs.get("max_tokens"),
                "temperature": kwargs.get("temperature"),
                "top_p": kwargs.get("top_p"),
                "top_k": kwargs.get("top_k"),
                "stop_sequences": kwargs.get("stop_sequences"),
                "thinking_budget_tokens": (kwargs.get("thinking") or {}).get("budget_tokens"),
                "tools_provided": [t.get("name") for t in (kwargs.get("tools") or [])],
                "tool_choice": kwargs.get("tool_choice"),
                "text": text,
                "thinking_text": thinking_text or None,
                "finish_reason": getattr(result, "stop_reason", None),
                "stop_sequence": getattr(result, "stop_sequence", None),
                "tool_uses": tool_uses or None,
                "response_id": getattr(result, "id", None),
                "usage": usage_dict,
                "elapsed_s": elapsed,
                "context": ctx,
            }
            record_llm_call({k: v for k, v in payload.items() if v is not None})
        except Exception:
            pass


class _FlowceptAnthropicStream:
    def __init__(self, ctx_mgr, kwargs, record_fn, t0):
        self._ctx_mgr = ctx_mgr
        self._kwargs = kwargs
        self._record_fn = record_fn
        self._t0 = t0
        self._stream = None

    def __enter__(self):
        self._stream = self._ctx_mgr.__enter__()
        return self._stream

    def __exit__(self, *args):
        import time as _time

        result = None
        try:
            result = self._stream.get_final_message()
        except Exception:
            pass
        if result is not None:
            self._record_fn(self._kwargs, result, _time.time() - self._t0)
        return self._ctx_mgr.__exit__(*args)


# ---------------------------------------------------------------------------
# Public plugin class
# ---------------------------------------------------------------------------


class FlowceptLangGraphPlugin:
    """
    FlowCept provenance plugin for LangGraph workflows.

    Captures the full provenance graph for each graph invocation:
    graph run → node tasks → LLM/tool child tasks, with CPU/memory telemetry
    and node enrichment.

    Parameters
    ----------
    config : dict, optional
        Plugin configuration keys:
          enabled       (bool, default True)
          workflow_name (str, default "langgraph-workflow")
          performance_tracking (bool, default True)
          perf_csv      (str, optional) — explicit path for timing CSV.

    Usage
    -----
    Option A — explicit start/stop::

        plugin = FlowceptLangGraphPlugin(config={...})
        plugin.start()
        result = graph.invoke(state, config={"callbacks": [plugin.callback_handler]})
        plugin.stop()

    Option B — context manager::

        with FlowceptLangGraphPlugin(config={...}) as plugin:
            result = graph.invoke(state, config={"callbacks": [plugin.callback_handler]})
    """

    def __init__(self, config: dict | None = None, _shared_interceptor=None) -> None:
        cfg = config or {}
        self._enabled: bool = cfg.get("enabled", True)
        self._workflow_name: str = cfg.get("workflow_name", "langgraph-workflow")
        self._campaign_id: str | None = cfg.get("campaign_id", None)
        self._perf_tracking: bool = cfg.get("performance_tracking", True)
        self._perf_csv: str | None = cfg.get("perf_csv", None)
        # When _shared_interceptor is supplied the plugin does NOT start/stop
        # its own Flowcept instance — it reuses the caller's buffer entirely.
        self._shared_interceptor = _shared_interceptor
        self._interceptor = _shared_interceptor or LangGraphInterceptor()
        self._owns_interceptor: bool = _shared_interceptor is None
        self._stats: _ProvenanceStats | None = None
        self._handler: FlowceptLangGraphCallback | None = None
        self._started = False

    @classmethod
    def from_academy_plugin(
        cls,
        academy_plugin: Any,
        config: dict | None = None,
    ) -> "FlowceptLangGraphPlugin":
        """Create a LangGraph plugin sharing an already-started FlowceptAcademyPlugin's buffer.

        All provenance records — from both Academy agents and LangGraph nodes —
        are written to the exact same FlowCept in-memory buffer and end up in
        the same JSONL file when the Academy plugin stops.

        Parameters
        ----------
        academy_plugin : FlowceptAcademyPlugin
            A plugin that has already been started (``plugin.start()`` called).
        config : dict, optional
            Same keys as FlowceptLangGraphPlugin.__init__ (enabled,
            performance_tracking, perf_csv).

        Returns
        -------
        FlowceptLangGraphPlugin
            A started plugin whose ``callback_handler`` is ready for use.

        Example
        -------
        ::

            academy_plugin = FlowceptAcademyPlugin(config={...}).start()
            lg_plugin = FlowceptLangGraphPlugin.from_academy_plugin(academy_plugin)
            # lg_plugin is already started — no need to call .start()
            result = graph.invoke(state, config={"callbacks": [lg_plugin.callback_handler]})
            # Stop only the Academy plugin; it flushes the shared buffer.
            academy_plugin.stop()
        """
        global _ACTIVE_INTERCEPTOR, _HANDLER_CLASS, _PROV_STATS
        # Inherit campaign_id from the academy plugin so all provenance is linked.
        academy_interceptor = academy_plugin._interceptor
        campaign_id = academy_interceptor._campaign_id
        merged = dict(config or {})
        merged["campaign_id"] = campaign_id
        # Create a proper LangGraphInterceptor (not an AcademyInterceptor).
        lg_interceptor = LangGraphInterceptor()
        lg_interceptor.start(
            merged.get("workflow_name", "langgraph-workflow"),
            campaign_id=campaign_id,
        )
        inst = cls(config=merged, _shared_interceptor=lg_interceptor)
        inst._interceptor = lg_interceptor
        inst._owns_interceptor = True  # we own this interceptor — stop it on stop()
        inst._started = True
        inst._stats = _ProvenanceStats() if merged.get("performance_tracking", True) else None
        if _HANDLER_CLASS is None:
            _HANDLER_CLASS = _build_handler_class()
        inst._handler = _HANDLER_CLASS(lg_interceptor, inst._stats)
        _ACTIVE_INTERCEPTOR = lg_interceptor
        _PROV_STATS = inst._stats
        return inst

    @property
    def callback_handler(self) -> FlowceptLangGraphCallback:
        """Return the LangChain callback handler to pass as ``config={"callbacks": [...]}``.

        Call ``start()`` before accessing this property.
        """
        if self._handler is None:
            raise RuntimeError("Plugin not started — call plugin.start() first.")
        return self._handler

    def start(self) -> "FlowceptLangGraphPlugin":
        """Start provenance capture and build the callback handler."""
        global _HANDLER_CLASS, _ACTIVE_INTERCEPTOR, _PROV_STATS
        if not self._enabled or self._started:
            return self
        if not self._owns_interceptor:
            # Already configured by from_academy_plugin(); nothing to start.
            return self
        try:
            self._stats = _ProvenanceStats() if self._perf_tracking else None
            _PROV_STATS = self._stats
            self._interceptor.start(self._workflow_name, campaign_id=self._campaign_id)
            self._campaign_id = self._interceptor._campaign_id

            if _HANDLER_CLASS is None:
                _HANDLER_CLASS = _build_handler_class()

            self._handler = _HANDLER_CLASS(self._interceptor, self._stats)
            self._started = True
            _ACTIVE_INTERCEPTOR = self._interceptor

            wf_id = self._interceptor._workflow_id
            campaign_id = self._interceptor._campaign_id
            print(
                f"[FlowceptLangGraphPlugin] Started\n"
                f"  workflow_id : {wf_id}\n"
                f"  campaign_id : {campaign_id}\n"
                f"  Capturing   : graph runs (sub-workflows), node execution "
                f"(parent_task_id), LLM + tool calls (child tasks, telemetry).",
                flush=True,
            )
        except Exception as e:
            print(
                f"[FlowceptLangGraphPlugin] WARNING: failed to start — {e!r}. Continuing without provenance capture.",
                flush=True,
            )
            _log.exception("FlowceptLangGraphPlugin start failed")
            self._enabled = False
        return self

    def stop(self) -> None:
        """Stop provenance capture, flush the buffer, and report overhead stats."""
        global _ACTIVE_INTERCEPTOR, _PROV_STATS
        if not self._started:
            return
        if not self._owns_interceptor:
            # Buffer is owned by the Academy plugin — do not stop or flush it here.
            # Just print the perf stats if enabled.
            self._started = False
            print(
                "[FlowceptLangGraphPlugin] Detached from shared buffer (buffer flushed by the owning plugin).",
                flush=True,
            )
            self._maybe_write_perf_csv()
            _ACTIVE_INTERCEPTOR = None
            _PROV_STATS = None
            return
        try:
            _t0 = time.perf_counter()
            self._interceptor.stop()
            if self._stats is not None:
                self._stats.record("flush", time.perf_counter() - _t0)
        except Exception as e:
            print(f"[FlowceptLangGraphPlugin] Warning during stop: {e!r}", flush=True)
        self._started = False
        print("[FlowceptLangGraphPlugin] Stopped.", flush=True)
        self._maybe_write_perf_csv()
        _PROV_STATS = None
        _ACTIVE_INTERCEPTOR = None

    def _maybe_write_perf_csv(self) -> None:

        if self._stats is not None:
            print(
                "\n[FlowceptLangGraphPlugin] Provenance overhead report:\n"
                + self._stats.summary()
                + "\n  (N = event count; Total/Mean/Min/Max in ms/µs respectively)\n",
                flush=True,
            )
            wf_id = self._interceptor._workflow_id
            csv_path = self._perf_csv or f"langgraph_provenance_perf_{wf_id}.csv"
            try:
                self._stats.to_csv(csv_path, workflow_id=wf_id)
                print(
                    f"[FlowceptLangGraphPlugin] Performance stats written to {csv_path}",
                    flush=True,
                )
            except Exception as e:
                print(
                    f"[FlowceptLangGraphPlugin] Warning: could not write perf CSV — {e!r}",
                    flush=True,
                )

    def __enter__(self) -> "FlowceptLangGraphPlugin":
        """Start the plugin when entering a ``with`` block."""
        return self.start()

    def __exit__(self, *_: Any) -> None:
        """Stop the plugin when leaving a ``with`` block."""
        self.stop()


# ---------------------------------------------------------------------------
# Serialisation helper (identical to flowcept_plugin.py)
# ---------------------------------------------------------------------------


def _safe_clip(obj: Any, _depth: int = 0) -> Any:
    """Recursively convert objects to JSON-serialisable form without truncation."""
    if _depth > 8:
        return str(obj)
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _safe_clip(v, _depth + 1) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_clip(v, _depth + 1) for v in obj]
    return repr(obj)


def _tel_to_dict(tel: Any) -> dict | None:
    if tel is None:
        return None
    try:
        return tel.to_dict()
    except Exception:
        return None
