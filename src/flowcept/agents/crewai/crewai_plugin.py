# academy_coscientist/plugins/flowcept_crewai_plugin.py
"""
FlowCept provenance plugin for CrewAI workflows.

Captures the full provenance graph for each crew kickoff using two complementary
CrewAI extension points:

  1. Event bus (BaseEventListener) — crew kickoff, task, and agent lifecycle events.
  2. LLM + Tool hooks (register_before/after_llm_call_hook,
     register_before/after_tool_call_hook) — richer LLM and tool provenance
     including full messages, response text, agent.role/goal/backstory,
     task.description/expected_output, iteration count, and typed tool inputs.

The event bus is used for lifecycle events (crew, task, agent).
The hooks replace the thin LLMCallStarted/Completed events with richer records.

Provenance hierarchy produced:
  WorkflowObject  (one per crew kickoff)
    └─ TaskObject  subtype=crewai_task      activity_id=<task_name>
         └─ TaskObject  subtype=crewai_agent  activity_id=<agent_role>
              └─ TaskObject  subtype=llm_call    activity_id=<model>
              └─ TaskObject  subtype=tool_call   activity_id=<tool_name>

Key FlowCept fields:
  task_id          — uuid per event (our own, not CrewAI's event_id)
  workflow_id      — global shared workflow id (setdefault pattern)
  campaign_id      — from Flowcept.campaign_id
  parent_task_id   — links agent → task, llm/tool → agent
  group_id         — all tasks within one crew kickoff share a group_id
  activity_id      — task name | agent role | model name | tool name
  subtype          — crewai_crew | crewai_task | crewai_agent | llm_call | tool_call
  used / generated — inputs and outputs
  status           — FINISHED | ERROR

Usage (two lines to wire up):

    plugin = FlowceptCrewAIPlugin(config={"workflow_name": "my-crew"})
    plugin.start()
    crew.kickoff()
    plugin.stop()

Or shared with an Academy plugin:

    academy_plugin = FlowceptAcademyPlugin(config={...}).start()
    crewai_plugin = FlowceptCrewAIPlugin.from_academy_plugin(academy_plugin)
    crew.kickoff()
    academy_plugin.stop()   # flushes the shared buffer
"""

from __future__ import annotations

import os
import time
import uuid
import threading
import logging
from contextlib import contextmanager
from typing import Any

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provenance overhead timer (identical to other plugins)
# ---------------------------------------------------------------------------


class _ProvenanceStats:
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
# CrewAI event listener — uses the native event bus
# ---------------------------------------------------------------------------


class _FlowceptCrewAIListener:
    """
    Listens to CrewAI's event bus and records provenance to a shared interceptor.

    Registered event pairs (start→end → ONE complete record each):
      CrewKickoffStarted/Completed  → crewai_crew  TaskObject + WorkflowObject
      TaskStarted/Completed         → crewai_task  TaskObject
      AgentExecutionStarted/Completed → crewai_agent TaskObject
      LLMCallStarted/Completed      → llm_call     TaskObject
      ToolUsageStarted/Finished     → tool_call    TaskObject
    """

    def __init__(self, interceptor: Any, stats: _ProvenanceStats | None) -> None:
        self._interceptor = interceptor
        self._stats = stats
        # Buffer: crew_kickoff event_id → {group_id, started_at, task_id, used, ...}
        self._crew_starts: dict[str, dict] = {}
        # crewai task event_id → {task_id, started_at, ...}
        self._task_starts: dict[str, dict] = {}
        # agent event_id → {task_id, started_at, ...}
        self._agent_starts: dict[str, dict] = {}
        # llm call_id → {task_id, started_at, ...}
        self._llm_starts: dict[str, dict] = {}
        # tool started_event_id → {task_id, started_at, ...}
        self._tool_starts: dict[str, dict] = {}
        # event_id → group_id for hierarchy linking
        self._crew_group: dict[str, str] = {}
        # task event_id → FlowCept task_id (so agent can reference it)
        self._task_fc_id: dict[str, str] = {}
        # agent event_id → FlowCept task_id (so llm/tool can reference it)
        self._agent_fc_id: dict[str, str] = {}

    def _record(self, category: str, elapsed: float) -> None:
        if self._stats is not None:
            self._stats.record(category, elapsed)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _safe_clip(self, obj: Any, depth: int = 0) -> Any:
        if depth > 6:
            return str(obj)
        if obj is None or isinstance(obj, (bool, int, float, str)):
            return obj
        if isinstance(obj, dict):
            return {str(k): self._safe_clip(v, depth + 1) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self._safe_clip(v, depth + 1) for v in obj]
        # For CrewAI objects: try model_dump, then repr
        try:
            if hasattr(obj, "model_dump"):
                return self._safe_clip(obj.model_dump(), depth + 1)
        except Exception:
            pass
        return repr(obj)

    def _intercept(self, task: dict) -> None:
        self._interceptor.intercept_task(task)

    # ── Crew Kickoff ─────────────────────────────────────────────────────────

    def on_crew_kickoff_started(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        group_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        crew_name = getattr(event, "crew_name", None) or "crew"
        inputs = self._safe_clip(getattr(event, "inputs", None) or {})
        event_id = getattr(event, "event_id", str(uuid.uuid4()))

        # Emit a sub-WorkflowObject for this kickoff so queries can navigate
        # the crew hierarchy
        self._interceptor.send_graph_workflow(crew_name, group_id)
        self._crew_group[event_id] = group_id

        self._crew_starts[event_id] = {
            "task_id": task_id,
            "subtype": "crewai_crew",
            "activity_id": crew_name,
            "group_id": group_id,
            "started_at": time.time(),
            "used": {"inputs": inputs, "crew_name": crew_name},
            "custom_metadata": {"crew_name": crew_name, "framework": "crewai"},
        }
        self._record("crew_kickoff_started", time.perf_counter() - t0)

    def on_crew_kickoff_completed(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", None)
        # CrewAI's completed event has started_event_id pointing back to start
        started_id = getattr(event, "started_event_id", None) or event_id
        skeleton = self._crew_starts.pop(started_id, None) or self._crew_starts.pop(event_id, {})

        output = self._safe_clip(getattr(event, "output", None))
        total_tokens = getattr(event, "total_tokens", None)

        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {"output": output, "total_tokens": total_tokens},
            }
        )
        self._intercept(skeleton)
        # Clean up group mapping
        self._crew_group.pop(started_id, None)
        self._crew_group.pop(event_id, None)
        self._record("crew_kickoff_completed", time.perf_counter() - t0)

    def on_crew_kickoff_failed(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", None)
        started_id = getattr(event, "started_event_id", None) or event_id
        skeleton = self._crew_starts.pop(started_id, {})
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "ERROR",
                "stderr": str(getattr(event, "error", "unknown error")),
            }
        )
        self._intercept(skeleton)
        self._record("crew_kickoff_failed", time.perf_counter() - t0)

    # ── Task ─────────────────────────────────────────────────────────────────

    def _find_group_id(self, event: Any) -> str | None:
        """Walk parent event chain to find the enclosing crew's group_id."""
        # CrewAI propagates task_name / agent_id through all events —
        # the group_id can be found via the triggered_by_event_id chain.
        # Simplest: scan _crew_group values (there's usually one active run).
        if self._crew_group:
            return next(iter(self._crew_group.values()))
        return None

    def on_task_started(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", str(uuid.uuid4()))
        task_id = str(uuid.uuid4())
        task_name = getattr(event, "task_name", None) or "task"
        agent_role = getattr(event, "agent_role", None) or "unknown"
        group_id = self._find_group_id(event)
        context = self._safe_clip(getattr(event, "context", None) or {})
        task_obj = self._safe_clip(getattr(event, "task", None))

        self._task_starts[event_id] = {
            "task_id": task_id,
            "subtype": "crewai_task",
            "activity_id": task_name,
            "group_id": group_id,
            "started_at": time.time(),
            "used": {"context": context, "task": task_obj},
            "custom_metadata": {
                "task_name": task_name,
                "agent_role": agent_role,
                "framework": "crewai",
            },
        }
        self._task_fc_id[event_id] = task_id
        self._record("task_started", time.perf_counter() - t0)

    def on_task_completed(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", None)
        started_id = getattr(event, "started_event_id", None) or event_id
        skeleton = self._task_starts.pop(started_id, None) or self._task_starts.pop(event_id, {})

        output = self._safe_clip(getattr(event, "output", None))
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {"output": output},
            }
        )
        self._intercept(skeleton)
        self._task_fc_id.pop(started_id, None)
        self._task_fc_id.pop(event_id, None)
        self._record("task_completed", time.perf_counter() - t0)

    def on_task_failed(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", None)
        started_id = getattr(event, "started_event_id", None) or event_id
        skeleton = self._task_starts.pop(started_id, {})
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "ERROR",
                "stderr": str(getattr(event, "error", "unknown")),
            }
        )
        self._intercept(skeleton)
        self._record("task_failed", time.perf_counter() - t0)

    # ── Agent Execution ───────────────────────────────────────────────────────

    def on_agent_execution_started(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", str(uuid.uuid4()))
        task_id = str(uuid.uuid4())
        agent = getattr(event, "agent", None)
        agent_role = getattr(event, "agent_role", None) or (getattr(agent, "role", None) if agent else None) or "agent"
        group_id = self._find_group_id(event)
        task_prompt = self._safe_clip(getattr(event, "task_prompt", None) or "")
        tools = self._safe_clip([getattr(t, "name", str(t)) for t in (getattr(event, "tools", None) or [])])
        # Link to enclosing task's FlowCept task_id
        task_evt_id = getattr(event, "started_event_id", None) or getattr(event, "task_id", None)
        parent_task_id = self._task_fc_id.get(task_evt_id) if task_evt_id else None

        skeleton: dict = {
            "task_id": task_id,
            "subtype": "crewai_agent",
            "activity_id": agent_role,
            "group_id": group_id,
            "started_at": time.time(),
            "used": {"task_prompt": task_prompt, "tools": tools},
            "custom_metadata": {
                "agent_role": agent_role,
                "framework": "crewai",
            },
        }
        if parent_task_id:
            skeleton["parent_task_id"] = parent_task_id
        self._agent_starts[event_id] = skeleton
        self._agent_fc_id[event_id] = task_id
        self._record("agent_started", time.perf_counter() - t0)

    def on_agent_execution_completed(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", None)
        started_id = getattr(event, "started_event_id", None) or event_id
        skeleton = self._agent_starts.pop(started_id, None) or self._agent_starts.pop(event_id, {})

        output = self._safe_clip(getattr(event, "output", None))
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {"output": output},
            }
        )
        self._intercept(skeleton)
        self._agent_fc_id.pop(started_id, None)
        self._agent_fc_id.pop(event_id, None)
        self._record("agent_completed", time.perf_counter() - t0)

    def on_agent_execution_error(self, source: Any, event: Any) -> None:
        t0 = time.perf_counter()
        event_id = getattr(event, "event_id", None)
        started_id = getattr(event, "started_event_id", None) or event_id
        skeleton = self._agent_starts.pop(started_id, {})
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "ERROR",
                "stderr": str(getattr(event, "error", "unknown")),
            }
        )
        self._intercept(skeleton)
        self._record("agent_error", time.perf_counter() - t0)

    # ── LLM + Tool calls are captured via hooks (see _FlowceptCrewAIHooks) ────
    # The event bus LLM/tool events are deliberately NOT registered here;
    # hooks provide richer data (full messages, agent/task objects, response text).


def _build_listener_class(interceptor: Any, stats: _ProvenanceStats | None):
    """
    Lazily build a concrete BaseEventListener subclass.

    Ensures crewai is only imported when the plugin is actually used.
    Registers only lifecycle events (crew, task, agent).
    LLM and tool calls are captured via hooks (richer data).
    """
    from crewai.events.base_event_listener import BaseEventListener
    from crewai.events.event_types import (
        CrewKickoffStartedEvent,
        CrewKickoffCompletedEvent,
        CrewKickoffFailedEvent,
        TaskStartedEvent,
        TaskCompletedEvent,
        TaskFailedEvent,
        AgentExecutionStartedEvent,
        AgentExecutionCompletedEvent,
        AgentExecutionErrorEvent,
    )

    _listener = _FlowceptCrewAIListener(interceptor, stats)

    class _ConcreteListener(BaseEventListener):
        def setup_listeners(self, bus) -> None:
            bus.on(CrewKickoffStartedEvent)(_listener.on_crew_kickoff_started)
            bus.on(CrewKickoffCompletedEvent)(_listener.on_crew_kickoff_completed)
            bus.on(CrewKickoffFailedEvent)(_listener.on_crew_kickoff_failed)
            bus.on(TaskStartedEvent)(_listener.on_task_started)
            bus.on(TaskCompletedEvent)(_listener.on_task_completed)
            bus.on(TaskFailedEvent)(_listener.on_task_failed)
            bus.on(AgentExecutionStartedEvent)(_listener.on_agent_execution_started)
            bus.on(AgentExecutionCompletedEvent)(_listener.on_agent_execution_completed)
            bus.on(AgentExecutionErrorEvent)(_listener.on_agent_execution_error)

    return _listener, _ConcreteListener()


# ---------------------------------------------------------------------------
# Hook-based LLM + Tool provenance (richer than event bus events)
# ---------------------------------------------------------------------------


class _FlowceptCrewAIHooks:
    """
    Registers CrewAI's before/after LLM and tool hooks to capture rich provenance.

    LLM hooks give:
      - Full message list (context.messages)  — not just serialised dicts
      - Actual response text (context.response)
      - agent.role, agent.goal, agent.backstory
      - task.description, task.expected_output
      - iterations (current ReAct loop count)

    Tool hooks give:
      - Typed tool_input dict (not a string)
      - tool_result string
      - agent, task, crew references
    """

    def __init__(
        self,
        interceptor: Any,
        stats: _ProvenanceStats | None,
        listener: _FlowceptCrewAIListener,
    ) -> None:
        self._interceptor = interceptor
        self._stats = stats
        self._listener = listener  # shares group_id / agent_fc_id state
        # Keyed by id(context.executor): before hook stores skeleton,
        # after hook pops and emits.  CrewAI creates new context objects for
        # each hook invocation so the context itself cannot be used as scratchpad.
        self._pending_llm: dict[int, dict] = {}
        self._pending_tool: dict[int, dict] = {}

    def _record(self, category: str, elapsed: float) -> None:
        if self._stats is not None:
            self._stats.record(category, elapsed)

    def _safe_clip(self, obj: Any, depth: int = 0) -> Any:
        return self._listener._safe_clip(obj, depth)

    # ── Before-LLM hook ──────────────────────────────────────────────────────

    def before_llm_call(self, context: Any) -> None:
        """Buffers the LLM call start skeleton; matched by after_llm_call."""
        t0 = time.perf_counter()
        task_id = str(uuid.uuid4())
        group_id = self._listener._find_group_id(None)

        # Rich context from the hook
        agent = getattr(context, "agent", None)
        task_obj = getattr(context, "task", None)
        llm = getattr(context, "llm", None)
        messages = getattr(context, "messages", [])
        iterations = getattr(context, "iterations", 0)

        model = getattr(llm, "model", None) or getattr(llm, "model_name", None) or "unknown"
        agent_role = getattr(agent, "role", None) or "unknown"

        # Retrieve enclosing agent's FlowCept task_id for parent linkage
        # The agent_fc_id map is keyed by CrewAI event_id; best-effort lookup
        parent_task_id = next(iter(self._listener._agent_fc_id.values()), None) if self._listener._agent_fc_id else None

        serialized_messages = self._safe_clip(
            [{"role": getattr(m, "role", "user"), "content": getattr(m, "content", str(m))} for m in messages]
            if messages and hasattr(messages[0], "role")
            else messages
        )

        used: dict = {
            "messages": serialized_messages,
            "model": model,
            "iterations": iterations,
            "agent_role": agent_role,
            "agent_goal": self._safe_clip(getattr(agent, "goal", None)),
            "task_description": self._safe_clip(getattr(task_obj, "description", None)),
        }

        skeleton: dict = {
            "task_id": task_id,
            "subtype": "llm_call",
            "activity_id": model,
            "group_id": group_id,
            "started_at": time.time(),
            "used": used,
            "custom_metadata": {
                "model": model,
                "agent_role": agent_role,
                "framework": "crewai",
                "source": "llm_hook",
            },
        }
        if parent_task_id:
            skeleton["parent_task_id"] = parent_task_id

        # CrewAI creates NEW context objects for before vs after hooks so we
        # cannot store state on the context.  Key by executor id instead —
        # each executor handles one LLM call at a time (sequential).
        key = id(getattr(context, "executor", context))
        self._pending_llm[key] = skeleton
        self._record("llm_hook_before", time.perf_counter() - t0)

    # ── After-LLM hook ───────────────────────────────────────────────────────

    def after_llm_call(self, context: Any) -> None:
        """Completes the skeleton buffered by before_llm_call and emits it."""
        t0 = time.perf_counter()
        key = id(getattr(context, "executor", context))
        skeleton: dict = self._pending_llm.pop(key, {})
        response = getattr(context, "response", None) or ""
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {
                    "response": response[:4000] if isinstance(response, str) else self._safe_clip(response),
                    "model": skeleton.get("activity_id", "unknown"),
                },
            }
        )
        self._interceptor.intercept_task(skeleton)
        self._record("llm_hook_after", time.perf_counter() - t0)

    # ── Before-tool hook ─────────────────────────────────────────────────────

    def before_tool_call(self, context: Any) -> None:
        """Buffers the tool call start skeleton."""
        t0 = time.perf_counter()
        task_id = str(uuid.uuid4())
        tool_name = getattr(context, "tool_name", None) or "tool"
        group_id = self._listener._find_group_id(None)

        agent = getattr(context, "agent", None)
        task_obj = getattr(context, "task", None)
        agent_role = getattr(agent, "role", None) or "unknown"

        parent_task_id = next(iter(self._listener._agent_fc_id.values()), None) if self._listener._agent_fc_id else None

        skeleton: dict = {
            "task_id": task_id,
            "subtype": "tool_call",
            "activity_id": tool_name,
            "group_id": group_id,
            "started_at": time.time(),
            "used": {
                "input": self._safe_clip(getattr(context, "tool_input", {})),
                "agent_role": agent_role,
                "task_description": self._safe_clip(getattr(task_obj, "description", None)),
            },
            "custom_metadata": {
                "tool_name": tool_name,
                "agent_role": agent_role,
                "framework": "crewai",
                "source": "tool_hook",
            },
        }
        if parent_task_id:
            skeleton["parent_task_id"] = parent_task_id

        key = id(getattr(context, "executor", context))
        self._pending_tool[key] = skeleton
        self._record("tool_hook_before", time.perf_counter() - t0)

    # ── After-tool hook ──────────────────────────────────────────────────────

    def after_tool_call(self, context: Any) -> None:
        """Completes the skeleton buffered by before_tool_call and emits it."""
        t0 = time.perf_counter()
        key = id(getattr(context, "executor", context))
        skeleton: dict = self._pending_tool.pop(key, {})
        result = getattr(context, "tool_result", None) or ""
        skeleton.update(
            {
                "ended_at": time.time(),
                "status": "FINISHED",
                "generated": {"output": result[:2000] if isinstance(result, str) else self._safe_clip(result)},
            }
        )
        self._interceptor.intercept_task(skeleton)
        self._record("tool_hook_after", time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# Shared interceptor wrapper (re-uses AcademyInterceptor when available)
# ---------------------------------------------------------------------------


class _CrewAIInterceptor:
    """Standalone interceptor for CrewAI provenance (Dask-style)."""

    def __init__(self) -> None:
        self._interceptor = None
        self._workflow_id: str | None = None
        self._campaign_id: str | None = None

    def start(self, workflow_name: str, campaign_id: str | None = None) -> None:
        from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        self._workflow_id = str(uuid.uuid4())
        self._campaign_id = campaign_id or str(uuid.uuid4())

        self._interceptor = BaseInterceptor(kind="crewai")
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
        if self._interceptor is None:
            return
        try:
            self._interceptor.stop(check_safe_stops=False)
        except Exception as e:
            _log.warning("Interceptor stop error: %r", e)
        self._interceptor = None

    def send_graph_workflow(self, name: str, group_id: str) -> str:
        if self._interceptor is None:
            return str(uuid.uuid4())
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        wf = WorkflowObject()
        wf.workflow_id = str(uuid.uuid4())
        wf.name = name
        wf.campaign_id = self._campaign_id
        wf.parent_workflow_id = self._workflow_id
        wf.custom_metadata = {"group_id": group_id, "framework": "crewai"}
        self._interceptor.send_workflow_message(wf)
        return wf.workflow_id

    def intercept_task(self, task_dict: dict) -> None:
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
    """
    Wrap an ``anthropic.Anthropic`` (or ``AsyncAnthropic``) client for provenance capture.

    Records every ``messages.create`` / ``messages.stream`` call as a FlowCept
    provenance record (subtype=llm_call) via ``record_llm_call()``.

    Usage::

        import anthropic
        from flowcept.agents.crewai.crewai_plugin import FlowceptAnthropicClient

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
        """Delegate attribute access to the wrapped client."""
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


class FlowceptCrewAIPlugin:
    """
    FlowCept provenance plugin for CrewAI workflows.

    Registers a listener on CrewAI's native event bus so every crew kickoff,
    task, agent execution, LLM call, and tool usage is captured automatically.

    Parameters
    ----------
    config : dict, optional
        Plugin configuration keys:
          enabled              (bool, default True)
          workflow_name        (str, default "crewai-workflow")
          performance_tracking (bool, default True)
          perf_csv             (str, optional) — explicit path for timing CSV.

    Usage
    -----
    Standalone::

        plugin = FlowceptCrewAIPlugin(config={"workflow_name": "my-crew"})
        plugin.start()
        crew.kickoff()
        plugin.stop()

    Shared with Academy plugin::

        academy_plugin = FlowceptAcademyPlugin(config={...}).start()
        crewai_plugin  = FlowceptCrewAIPlugin.from_academy_plugin(academy_plugin)
        crew.kickoff()
        academy_plugin.stop()   # flushes the shared buffer
    """

    def __init__(self, config: dict | None = None, _shared_interceptor=None) -> None:
        cfg = config or {}
        self._enabled: bool = cfg.get("enabled", True)
        self._workflow_name: str = cfg.get("workflow_name", "crewai-workflow")
        self._campaign_id: str | None = cfg.get("campaign_id", None)
        self._perf_tracking: bool = cfg.get("performance_tracking", True)
        self._perf_csv: str | None = cfg.get("perf_csv", None)
        self._shared_interceptor = _shared_interceptor
        self._interceptor = _shared_interceptor or _CrewAIInterceptor()
        self._owns_interceptor: bool = _shared_interceptor is None
        self._stats: _ProvenanceStats | None = None
        self._listener_obj: _FlowceptCrewAIListener | None = None
        self._hooks_obj: _FlowceptCrewAIHooks | None = None
        self._started = False

    def _register_hooks(self) -> None:
        from crewai.hooks.llm_hooks import (
            register_before_llm_call_hook,
            register_after_llm_call_hook,
        )
        from crewai.hooks.tool_hooks import (
            register_before_tool_call_hook,
            register_after_tool_call_hook,
        )

        register_before_llm_call_hook(self._hooks_obj.before_llm_call)
        register_after_llm_call_hook(self._hooks_obj.after_llm_call)
        register_before_tool_call_hook(self._hooks_obj.before_tool_call)
        register_after_tool_call_hook(self._hooks_obj.after_tool_call)

    def _unregister_hooks(self) -> None:
        if self._hooks_obj is None:
            return
        try:
            from crewai.hooks.llm_hooks import (
                unregister_before_llm_call_hook,
                unregister_after_llm_call_hook,
            )
            from crewai.hooks.tool_hooks import (
                unregister_before_tool_call_hook,
                unregister_after_tool_call_hook,
            )

            unregister_before_llm_call_hook(self._hooks_obj.before_llm_call)
            unregister_after_llm_call_hook(self._hooks_obj.after_llm_call)
            unregister_before_tool_call_hook(self._hooks_obj.before_tool_call)
            unregister_after_tool_call_hook(self._hooks_obj.after_tool_call)
        except Exception as e:
            _log.debug("Hook unregister warning: %r", e)

    @classmethod
    def from_academy_plugin(
        cls,
        academy_plugin: Any,
        config: dict | None = None,
    ) -> "FlowceptCrewAIPlugin":
        """
        Create a CrewAI plugin that shares the buffer of a running FlowceptAcademyPlugin.

        All provenance records land in the same JSONL file when the Academy
        plugin stops.
        """
        interceptor = academy_plugin._interceptor
        inst = cls(config=config, _shared_interceptor=interceptor)
        inst._started = True
        global _ACTIVE_INTERCEPTOR
        _ACTIVE_INTERCEPTOR = interceptor

        inst._stats = _ProvenanceStats() if (config or {}).get("performance_tracking", True) else None
        listener_obj, _ = _build_listener_class(interceptor, inst._stats)
        inst._listener_obj = listener_obj
        inst._hooks_obj = _FlowceptCrewAIHooks(interceptor, inst._stats, listener_obj)
        inst._register_hooks()
        global _PROV_STATS
        _PROV_STATS = inst._stats
        return inst

    def start(self) -> "FlowceptCrewAIPlugin":
        """Start provenance capture: register listeners, hooks, and the interceptor."""
        if not self._enabled or self._started:
            return self
        if not self._owns_interceptor:
            return self
        try:
            self._stats = _ProvenanceStats() if self._perf_tracking else None
            global _PROV_STATS
            _PROV_STATS = self._stats
            self._interceptor.start(self._workflow_name, campaign_id=self._campaign_id)
            self._campaign_id = self._interceptor._campaign_id
            listener_obj, _ = _build_listener_class(self._interceptor, self._stats)
            self._listener_obj = listener_obj
            self._hooks_obj = _FlowceptCrewAIHooks(self._interceptor, self._stats, listener_obj)
            self._register_hooks()
            self._started = True
            global _ACTIVE_INTERCEPTOR
            _ACTIVE_INTERCEPTOR = self._interceptor
            wf_id = self._interceptor._workflow_id
            print(
                f"[FlowceptCrewAIPlugin] Started\n"
                f"  workflow_id : {wf_id}\n"
                f"  campaign_id : {self._interceptor._campaign_id}\n"
                f"  Capturing   : crew/task/agent (event bus) + "
                f"LLM/tool (hooks — full messages, response, agent context).",
                flush=True,
            )
        except Exception as e:
            print(
                f"[FlowceptCrewAIPlugin] WARNING: failed to start — {e!r}. Continuing without provenance capture.",
                flush=True,
            )
            _log.exception("FlowceptCrewAIPlugin start failed")
            self._enabled = False
        return self

    def stop(self) -> None:
        """Stop provenance capture: unregister hooks and flush records."""
        if not self._started:
            return
        self._unregister_hooks()
        if not self._owns_interceptor:
            self._started = False
            print(
                "[FlowceptCrewAIPlugin] Detached from shared buffer (flushed by the owning plugin).",
                flush=True,
            )
            self._maybe_write_perf_csv()
            global _PROV_STATS
            _PROV_STATS = None
            return
        try:
            _t0 = time.perf_counter()
            self._interceptor.stop()
            if self._stats is not None:
                self._stats.record("flush", time.perf_counter() - _t0)
        except Exception as e:
            print(f"[FlowceptCrewAIPlugin] Warning during stop: {e!r}", flush=True)
        self._started = False
        print("[FlowceptCrewAIPlugin] Stopped.", flush=True)
        self._maybe_write_perf_csv()
        global _ACTIVE_INTERCEPTOR
        _ACTIVE_INTERCEPTOR = None
        _PROV_STATS = None

    def _maybe_write_perf_csv(self) -> None:
        if self._stats is None:
            return
        print(
            "\n[FlowceptCrewAIPlugin] Provenance overhead report:\n"
            + self._stats.summary()
            + "\n  (N = event count; Total/Mean/Min/Max in ms/µs respectively)\n",
            flush=True,
        )
        wf_id = self._interceptor._workflow_id
        csv_path = self._perf_csv or f"crewai_provenance_perf_{wf_id}.csv"
        try:
            self._stats.to_csv(csv_path, workflow_id=wf_id)
            print(f"[FlowceptCrewAIPlugin] Performance stats → {csv_path}", flush=True)
        except Exception as e:
            print(f"[FlowceptCrewAIPlugin] Warning: could not write perf CSV — {e!r}", flush=True)

    def __enter__(self) -> "FlowceptCrewAIPlugin":
        """Start the plugin when entering a context manager block."""
        return self.start()

    def __exit__(self, *_: Any) -> None:
        """Stop the plugin when exiting a context manager block."""
        self.stop()
