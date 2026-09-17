# academy_coscientist/plugins/flowcept_plugin.py
"""
Generic FlowCept provenance plugin for Academy-based applications.

Designed around FlowCept's provenance model (TaskObject, WorkflowObject,
TelemetryCapture, Status).

Provenance hierarchy produced:
  WorkflowObject  (one per run — top-level workflow)
    └─ WorkflowObject  (one per agent — sub-workflow, parent_workflow_id → top)
         └─ TaskObject  activity_id=action_name      subtype=academy_action
              └─ TaskObject  activity_id=llm_call_type  subtype=llm_call  (parent_task_id)
         └─ TaskObject  activity_id=loop_name         subtype=academy_loop
         └─ TaskObject  activity_id=agent_startup|shutdown  subtype=academy_lifecycle

Key FlowCept fields used correctly:
  task_id                    — uuid per task record
  workflow_id                — per-agent sub-workflow id (linked to top-level via parent)
  campaign_id                — from Flowcept.campaign_id
  parent_task_id             — LLM tasks are children of the action that spawned them
  group_id                   — loop events share a group_id for grouping
  activity_id                — action name, llm call type, loop name, lifecycle event
  subtype                    — academy_action | academy_loop | academy_lifecycle | llm_call
  used / generated           — inputs and outputs
  status                     — proper Status enum values (FINISHED | ERROR)
  telemetry_at_start/end     — CPU/memory snapshots via TelemetryCapture
  node_name, hostname, etc.  — via TaskObject.enrich_task_dict()

LLM calls are linked to their parent action via a contextvars.ContextVar so that
any LLM call happening inside an async action is automatically a child of that action.

Usage (zero agent code changes required):

    import my_llm_logging
    plugin = FlowceptAcademyPlugin(
        config={"workflow_name": "my-app"},
        llm_hook_register=my_llm_logging.register_llm_hook,
        llm_hook_unregister=my_llm_logging.unregister_llm_hook,
    )
    plugin.start()
    try:
        asyncio.run(my_academy_app())
    finally:
        plugin.stop()

LLM hook contract:
    The hook function receives a dict payload with at minimum:
      "type"     — one of: parsed_json_result | chat_completion |
                           embed_result_local | embed_result_openai
      "context"  — dict of caller-supplied key/value tags (agent, call_type, ...)
      "model"    — model identifier string
    All top-level fields from parsed JSON responses are automatically hoisted
    into the generated record so they are directly queryable.
"""

from __future__ import annotations

import os

import contextvars
import json as _json
import logging
import threading
import time
import uuid
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from concurrent.futures import ProcessPoolExecutor


# ---------------------------------------------------------------------------
# Provenance overhead timer
# ---------------------------------------------------------------------------


class _ProvenanceStats:
    """
    Lightweight thread-safe accumulator for provenance capture timings.

    Records call counts, total/min/max wall-clock elapsed time (seconds) per
    named *category*.  All arithmetic uses ``time.perf_counter()`` so the
    resolution is sub-microsecond on all supported platforms.

    Categories captured automatically:
      ``action_emit``   — time spent inside ``_emit_action()``
      ``loop_emit``     — time spent inside ``_emit_loop_event()``
      ``lifecycle_emit``— time spent inside ``_emit_lifecycle()``
      ``llm_hook``      — time spent processing each LLM call in ``_on_llm_call()``
      ``intercept_task``— time spent inside ``AcademyInterceptor.intercept_task()``
                          (serialisation + buffer append)
      ``flush``         — wall-clock time for ``stop()``
    """

    __slots__ = ("_lock", "_counts", "_totals", "_mins", "_maxs", "_raw")

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._counts: dict[str, int] = {}
        self._totals: dict[str, float] = {}
        self._mins: dict[str, float] = {}
        self._maxs: dict[str, float] = {}
        # Raw per-event buffer: list of (timestamp_utc, category, elapsed_s)
        self._raw: list[tuple[str, str, float]] = []

    def record(self, category: str, elapsed: float) -> None:
        """Add one observation for *category* (elapsed in seconds)."""
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
        """Return a formatted table of all recorded categories."""
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
        """Append one row per captured event to a CSV file (header written once).

        Each row is one individual provenance-capture observation so the file
        can be used for distribution analysis, percentile queries, or time-series
        plots without losing any detail.

        Columns
        -------
        timestamp_utc, workflow_id, category, elapsed_us
        """
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

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()
            self._totals.clear()
            self._mins.clear()
            self._maxs.clear()
            self._raw.clear()


# Module-level singleton; activated when the plugin starts.
_PROV_STATS: _ProvenanceStats | None = None


@contextmanager
def _timed(category: str):
    """Context manager: record wall-clock time for *category* in ``_PROV_STATS``."""
    t0 = time.perf_counter()
    try:
        yield
    finally:
        if _PROV_STATS is not None:
            _PROV_STATS.record(category, time.perf_counter() - t0)


_log = logging.getLogger(__name__)

# ContextVar: holds the task_id of the currently-executing Academy action (or
# loop) so that LLM calls made inside it can be registered as child tasks.
_current_action_task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_action_task_id", default=None
)

# ContextVar: holds the real Academy agent ID (e.g. "AgentId<82278eb6>") for
# the agent whose coroutine is currently executing.  Set once per agent at
# startup so every LLM call emitted from within that agent carries the right ID.
_current_academy_agent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_academy_agent_id", default=None
)

# LLM payload types that carry a complete request+response pair.
_CAPTURE_LLM_TYPES = frozenset(
    {
        "parsed_json_result",
        "chat_completion",
        "embed_result_local",
        "embed_result_openai",
    }
)


# ---------------------------------------------------------------------------
# Academy interceptor — manages BaseInterceptor directly (Dask-style)
# ---------------------------------------------------------------------------


class AcademyInterceptor:
    """
    Wrap FlowCept's BaseInterceptor directly (Dask-style).

    Exposes:
      - start(workflow_name)       — initialises the interceptor and MQDao
      - stop()                     — flushes and closes the interceptor
      - intercept_task(task_dict)  — enriches with FlowCept standard fields and sends
      - send_agent_workflow(...)   — emits a WorkflowObject for an agent
      - telemetry_capture          — the underlying TelemetryCapture instance.
    """

    def __init__(self) -> None:
        self._interceptor = None
        self._workflow_id: str | None = None
        self._campaign_id: str | None = None

    def start(self, workflow_name: str, campaign_id: str | None = None) -> None:
        """Initialize the interceptor and emit the top-level workflow record."""
        from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        self._workflow_id = str(uuid.uuid4())
        self._campaign_id = campaign_id or str(uuid.uuid4())

        # Create a fresh BaseInterceptor directly (Dask-style — no Flowcept controller)
        self._interceptor = BaseInterceptor(kind="academy")
        self._interceptor.start(
            bundle_exec_id=self._workflow_id,
            check_safe_stops=False,
        )

        # Emit the top-level workflow record
        wf = WorkflowObject()
        wf.workflow_id = self._workflow_id
        wf.campaign_id = self._campaign_id
        wf.name = workflow_name
        self._interceptor.send_workflow_message(wf)

    def start_worker(self, workflow_id: str, campaign_id: str) -> None:
        """
        Initialize this interceptor inside a worker process sharing an existing workflow.

        Unlike ``start()``, this method reuses the provided *workflow_id* and
        *campaign_id* (already emitted by the parent process) so that all
        provenance records from every worker process appear under the same
        top-level WorkflowObject.  No new WorkflowObject is emitted.

        Called automatically by ``_worker_init()``; use ``make_process_executor()``
        rather than calling this directly.
        """
        from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor

        self._workflow_id = workflow_id
        self._campaign_id = campaign_id
        self._interceptor = BaseInterceptor(kind="academy")
        self._interceptor.start(
            bundle_exec_id=self._workflow_id,
            check_safe_stops=False,
        )

    def stop(self) -> None:
        """Flush and close the underlying interceptor."""
        if self._interceptor is None:
            return
        with _timed("flush"):
            try:
                self._interceptor.stop(check_safe_stops=False)
            except Exception as e:
                _log.warning("Interceptor stop error: %r", e)
        self._interceptor = None

    @property
    def telemetry_capture(self):
        """Return the underlying TelemetryCapture instance, or None if not started."""
        return self._interceptor.telemetry_capture if self._interceptor else None

    def send_agent_workflow(self, agent_type: str, agent_id: str) -> str:
        """Emit a WorkflowObject for an agent sub-workflow; return its workflow_id."""
        if self._interceptor is None:
            return str(uuid.uuid4())
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        wf = WorkflowObject()
        wf.workflow_id = str(uuid.uuid4())
        wf.name = f"{agent_type}:{agent_id}"
        wf.campaign_id = self._campaign_id
        wf.parent_workflow_id = self._workflow_id
        wf.custom_metadata = {"agent_type": agent_type, "agent_id": agent_id}
        self._interceptor.send_workflow_message(wf)
        return wf.workflow_id

    def send_graph_workflow(self, graph_name: str, group_id: str) -> str:
        """Emit a WorkflowObject for a LangGraph run sub-workflow; return its workflow_id.

        Same structure as send_agent_workflow but with graph-oriented metadata.
        Allows AcademyInterceptor to serve as the shared interceptor for both
        FlowceptAcademyPlugin and FlowceptLangGraphPlugin so that all provenance
        records go into the same FlowCept buffer.
        """
        if self._interceptor is None:
            return str(uuid.uuid4())
        from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject

        wf = WorkflowObject()
        wf.workflow_id = str(uuid.uuid4())
        wf.name = graph_name
        wf.campaign_id = self._campaign_id
        wf.parent_workflow_id = self._workflow_id
        wf.custom_metadata = {"graph_name": graph_name, "group_id": group_id}
        self._interceptor.send_workflow_message(wf)
        return wf.workflow_id

    def intercept_task(self, task_dict: dict) -> None:
        """Enrich task_dict with FlowCept standard fields and append to buffer."""
        if self._interceptor is None:
            return
        with _timed("intercept_task"):
            from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
            from flowcept.commons.vocabulary import Status

            task_dict.setdefault("type", "task")
            task_dict.setdefault("task_id", str(uuid.uuid4()))
            task_dict.setdefault("workflow_id", self._workflow_id)
            task_dict.setdefault("campaign_id", self._campaign_id)

            # Normalise status to proper enum value
            raw = task_dict.get("status", "FINISHED")
            if isinstance(raw, str):
                try:
                    task_dict["status"] = Status[raw].value
                except KeyError:
                    task_dict["status"] = Status.FINISHED.value

            # Enrich with node_name, login_name, hostname, public_ip, private_ip
            TaskObject.enrich_task_dict(task_dict)

            self._interceptor.intercept(task_dict)


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

_PATCHER_INSTALLED: bool = False
_ACTIVE_INTERCEPTOR: AcademyInterceptor | None = None
_ORIG_PPE_INIT = None  # holds the original ProcessPoolExecutor.__init__ while patched
_PERF_CSV_PATH: str | None = None  # set by plugin.start(); forwarded to workers via initargs
_WORKER_PERF_CSV: str | None = None  # set inside each worker by _worker_init

# Per-agent sub-workflow IDs  {agent_id_str -> sub_workflow_id}
_AGENT_WORKFLOWS: dict[str, str] = {}

# Reverse map: Academy agent ID → agent class name, for enriching records that
# only have the academy ID (e.g. embed calls whose ctx has no "agent" key).
_AGENT_ID_TO_TYPE: dict[str, str] = {}


# ---------------------------------------------------------------------------
# Process-pool support — picklable worker initializer + executor factory
# ---------------------------------------------------------------------------


def _worker_init(workflow_id: str, campaign_id: str, perf_tracking: bool, perf_csv: str | None = None) -> None:
    """
    ``ProcessPoolExecutor`` initializer for Flowcept provenance capture.

    Called automatically once per worker process before any agents run.
    Sets up a fresh ``AcademyInterceptor`` that shares the parent's
    *workflow_id* and *campaign_id* so all records appear in the same
    provenance graph, patches ``academy.runtime.Runtime``, and registers
    an atexit handler to flush the buffer when the worker exits.

    Do not call directly — use ``make_process_executor()`` instead.
    """
    import atexit

    global _ACTIVE_INTERCEPTOR, _PROV_STATS, _WORKER_PERF_CSV
    _WORKER_PERF_CSV = perf_csv
    try:
        interceptor = AcademyInterceptor()
        interceptor.start_worker(workflow_id, campaign_id)
        _ACTIVE_INTERCEPTOR = interceptor
        _install_runtime_patches()
        _PROV_STATS = _ProvenanceStats() if perf_tracking else None
        atexit.register(_worker_shutdown)
    except Exception as e:
        _log.warning("[Flowcept] Worker process init failed: %r — provenance disabled in this worker.", e)


def _worker_shutdown() -> None:
    """
    Atexit handler registered by ``_worker_init``.

    Flushes the worker's local provenance buffer to the MQ before the
    process exits, ensuring no records are lost.  Also appends this
    worker's per-category timing rows to the shared perf CSV so that
    action_emit / loop_emit / etc. from worker processes appear alongside
    the main process's flush row.
    """
    global _ACTIVE_INTERCEPTOR
    interceptor = _ACTIVE_INTERCEPTOR
    if interceptor is None:
        return
    wf_id = interceptor._workflow_id  # save before stop() clears _interceptor
    try:
        interceptor.stop()
    except Exception:
        pass
    _ACTIVE_INTERCEPTOR = None
    if _PROV_STATS is not None and _WORKER_PERF_CSV:
        try:
            _PROV_STATS.to_csv(_WORKER_PERF_CSV, workflow_id=wf_id)
        except Exception:
            pass


def _patch_process_pool_executor() -> None:
    """
    Monkey-patch ``ProcessPoolExecutor.__init__`` to inject ``_worker_init``.

    Any executor created while the Academy plugin is active automatically
    receives ``_worker_init`` as its initializer.

    Only injects when no ``initializer`` is already provided by the caller,
    so explicit user-supplied initializers are never overridden.
    Called by ``FlowceptAcademyPlugin.start()``.
    """
    global _ORIG_PPE_INIT
    from concurrent.futures import ProcessPoolExecutor

    if _ORIG_PPE_INIT is not None:
        return  # already patched

    _ORIG_PPE_INIT = ProcessPoolExecutor.__init__
    _orig = _ORIG_PPE_INIT  # capture for closure

    def _patched_init(self, max_workers=None, mp_context=None, initializer=None, initargs=(), **kw):
        interceptor = _ACTIVE_INTERCEPTOR
        if initializer is None and interceptor is not None:
            initializer = _worker_init
            initargs = (
                interceptor._workflow_id,
                interceptor._campaign_id,
                _PROV_STATS is not None,
                _PERF_CSV_PATH,
            )
        _orig(self, max_workers=max_workers, mp_context=mp_context, initializer=initializer, initargs=initargs, **kw)

    ProcessPoolExecutor.__init__ = _patched_init  # type: ignore[method-assign]


def _unpatch_process_pool_executor() -> None:
    """Restore the original ``ProcessPoolExecutor.__init__``. Called by ``stop()``."""
    global _ORIG_PPE_INIT
    if _ORIG_PPE_INIT is None:
        return
    from concurrent.futures import ProcessPoolExecutor

    ProcessPoolExecutor.__init__ = _ORIG_PPE_INIT  # type: ignore[method-assign]
    _ORIG_PPE_INIT = None


def make_process_executor(max_workers: int | None = None) -> "ProcessPoolExecutor":
    """
    Create a ``ProcessPoolExecutor`` with provenance capture pre-wired into every worker.

    Must be called while the Academy plugin is active — i.e., inside a
    ``with Flowcept():`` block after the plugin has started — so that the
    current ``workflow_id`` and ``campaign_id`` can be forwarded to workers.

    Each worker process receives its own ``AcademyInterceptor`` connected
    to the same MQ backend.  All task records carry the shared
    *workflow_id* / *campaign_id*, so the full provenance graph is coherent
    across processes.

    Parameters
    ----------
    max_workers : int, optional
        Number of worker processes.  Defaults to ``os.cpu_count()``.

    Returns
    -------
    ProcessPoolExecutor
        Pass directly to ``Manager.from_exchange_factory(executors=executor)``.

    Raises
    ------
    RuntimeError
        If called before the Academy plugin has started.

    Example
    -------
    ::

        from flowcept import Flowcept
        from flowcept.agents.academy.academy_plugin import make_process_executor

        with Flowcept():
            executor = make_process_executor(max_workers=4)
            async with await Manager.from_exchange_factory(
                factory=exchange, executors=executor,
            ) as manager:
                counter = await manager.launch(CounterAgent)
                ...
    """
    from concurrent.futures import ProcessPoolExecutor

    interceptor = _ACTIVE_INTERCEPTOR
    if interceptor is None:
        raise RuntimeError(
            "make_process_executor() must be called while the Flowcept Academy "
            "plugin is running (inside a 'with Flowcept():' block)."
        )
    return ProcessPoolExecutor(
        max_workers=max_workers,
        initializer=_worker_init,
        initargs=(
            interceptor._workflow_id,
            interceptor._campaign_id,
            _PROV_STATS is not None,
            _PERF_CSV_PATH,
        ),
    )


# ---------------------------------------------------------------------------
# Academy Runtime patcher
# ---------------------------------------------------------------------------


def _install_runtime_patches() -> None:
    """
    Patch academy.runtime.Runtime at the class level.

    Every Runtime instance (one per agent) captures provenance without any
    agent code changes.
    """
    global _PATCHER_INSTALLED
    if _PATCHER_INSTALLED:
        return

    from academy.runtime import Runtime

    # ---- @action dispatch ------------------------------------------------
    _orig_action = Runtime.action

    async def _action_with_prov(self, action: str, source_id: Any, *, args: Any, kwargs: Any) -> Any:
        interceptor = _ACTIVE_INTERCEPTOR
        if interceptor is None:
            return await _orig_action(self, action, source_id, args=args, kwargs=kwargs)

        tel_cap = interceptor.telemetry_capture
        task_id = str(uuid.uuid4())
        tel_start = tel_cap.capture() if tel_cap else None
        started_at = time.time()

        # Propagate action's task_id into context so nested LLM calls see it
        token = _current_action_task_id.set(task_id)
        error: BaseException | None = None
        result: Any = None
        try:
            result = await _orig_action(self, action, source_id, args=args, kwargs=kwargs)
            return result
        except Exception as exc:
            error = exc
            raise
        finally:
            _current_action_task_id.reset(token)
            ended_at = time.time()
            tel_end = tel_cap.capture() if tel_cap else None
            try:
                _emit_action(
                    interceptor,
                    self,
                    action,
                    source_id,
                    args,
                    kwargs,
                    result,
                    error,
                    task_id,
                    started_at,
                    ended_at,
                    tel_start,
                    tel_end,
                )
            except Exception:
                pass

    Runtime.action = _action_with_prov  # type: ignore[method-assign]

    # ---- @loop execution -------------------------------------------------
    _orig_execute_loop = Runtime._execute_loop

    async def _loop_with_prov(self, name: str, method: Any) -> None:
        interceptor = _ACTIVE_INTERCEPTOR
        if interceptor is None:
            return await _orig_execute_loop(self, name, method)

        tel_cap = interceptor.telemetry_capture
        task_id = str(uuid.uuid4())
        group_id = str(uuid.uuid4())
        tel_start = tel_cap.capture() if tel_cap else None
        t0 = time.time()
        _emit_loop_event(interceptor, self, name, "start", task_id, group_id, t0, tel_start)

        # Set context so LLM calls made inside the loop body are linked to
        # this loop task.  The action patch will override this for any
        # @action dispatches that happen concurrently.
        token = _current_action_task_id.set(task_id)
        try:
            await _orig_execute_loop(self, name, method)
            tel_end = tel_cap.capture() if tel_cap else None
            _emit_loop_event(interceptor, self, name, "exit", task_id, group_id, t0, tel_end)
        except Exception as exc:
            tel_end = tel_cap.capture() if tel_cap else None
            _emit_loop_event(interceptor, self, name, "error", task_id, group_id, t0, tel_end, error=exc)
            raise
        finally:
            _current_action_task_id.reset(token)

    Runtime._execute_loop = _loop_with_prov  # type: ignore[method-assign]

    # ---- agent startup ---------------------------------------------------
    _orig_start = Runtime._start

    async def _start_with_prov(self) -> None:
        # CRITICAL: set the ContextVar BEFORE calling _orig_start.
        #
        # Academy's _start() creates all loop tasks and the exchange listener
        # task via asyncio.create_task / spawn_guarded_background_task.  Each
        # new task gets a *copy* of the context at the moment of creation.
        # If we set the ContextVar after _orig_start returns, those tasks
        # already have stale context copies and will never see the agent ID.
        # Setting it first ensures every task spawned during startup inherits
        # the correct Academy agent ID automatically.
        agent_type, agent_id = _agent_info(self)
        _current_academy_agent_id.set(agent_id)

        await _orig_start(self)

        interceptor = _ACTIVE_INTERCEPTOR
        if interceptor is None:
            return
        try:
            sub_wf_id = interceptor.send_agent_workflow(agent_type, agent_id)
            _AGENT_WORKFLOWS[agent_id] = sub_wf_id
            _AGENT_ID_TO_TYPE[agent_id] = agent_type
            _emit_lifecycle(interceptor, self, "agent_startup")
        except Exception:
            pass

    Runtime._start = _start_with_prov  # type: ignore[method-assign]

    # ---- agent shutdown --------------------------------------------------
    _orig_shutdown = Runtime._shutdown

    async def _shutdown_with_prov(self) -> None:
        interceptor = _ACTIVE_INTERCEPTOR
        if interceptor is not None:
            try:
                _emit_lifecycle(interceptor, self, "agent_shutdown")
            except Exception:
                pass
        await _orig_shutdown(self)

    Runtime._shutdown = _shutdown_with_prov  # type: ignore[method-assign]

    _PATCHER_INSTALLED = True


def _uninstall_runtime_patches() -> None:
    """Clear the active interceptor so all patches become no-ops."""
    global _ACTIVE_INTERCEPTOR
    _ACTIVE_INTERCEPTOR = None
    _AGENT_WORKFLOWS.clear()
    _AGENT_ID_TO_TYPE.clear()


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


def _agent_info(runtime: Any) -> tuple[str, str]:
    try:
        agent_type = type(runtime.agent).__name__
    except Exception:
        agent_type = "unknown"
    try:
        agent_id = str(runtime.agent_id)
    except Exception:
        agent_id = "unknown"
    return agent_type, agent_id


def _agent_workflow_id(agent_id: str, fallback: str | None) -> str | None:
    return _AGENT_WORKFLOWS.get(agent_id, fallback)


def _parse_source(source_id: Any) -> tuple[str | None, str | None, str | None]:
    """
    Parse Academy source_id into (raw_str, agent_uid, source_workflow_id).

    source_id is either:
      - UserId<hex>  → a user/launcher, not an agent
      - AgentId<hex> → another agent; look up its sub-workflow
    Returns (source_str, source_agent_id, source_workflow_id).
    """
    s = str(source_id)
    if s.startswith("AgentId"):
        wf_id = _AGENT_WORKFLOWS.get(s)
        return s, s, wf_id
    return s, None, None


def _tel_to_dict(tel: Any) -> dict | None:
    if tel is None:
        return None
    try:
        return tel.to_dict()
    except Exception:
        return None


def _emit_action(
    interceptor: AcademyInterceptor,
    runtime: Any,
    action: str,
    source_id: Any,
    args: Any,
    kwargs: Any,
    result: Any,
    error: BaseException | None,
    task_id: str,
    started_at: float,
    ended_at: float,
    tel_start: Any,
    tel_end: Any,
) -> None:
    with _timed("action_emit"):
        agent_type, agent_id = _agent_info(runtime)
        source_str, source_agent_id, source_workflow_id = _parse_source(source_id)

        custom: dict[str, Any] = {
            "agent_type": agent_type,
            "source_id": source_str,
            # Always record whether this was a cross-agent call
            "cross_agent_call": source_agent_id is not None,
        }
        if source_agent_id is not None:
            # Explicit inter-agent provenance: who called this action and from
            # which sub-workflow, so the full agent-to-agent graph is queryable.
            custom["source_agent_id"] = source_agent_id
            if source_workflow_id is not None:
                custom["source_workflow_id"] = source_workflow_id

        task: dict[str, Any] = {
            "task_id": task_id,
            "subtype": "academy_action",
            "activity_id": action,
            "agent_id": agent_id,
            "custom_metadata": custom,
            "started_at": started_at,
            "ended_at": ended_at,
            "status": "ERROR" if error else "FINISHED",
            "used": {"args": _safe_clip(args), "kwargs": _safe_clip(kwargs)},
            "generated": _safe_clip(result) if error is None else None,
            "stderr": str(error) if error else None,
        }
        if tel_start is not None:
            task["telemetry_at_start"] = _tel_to_dict(tel_start)
        if tel_end is not None:
            task["telemetry_at_end"] = _tel_to_dict(tel_end)
        interceptor.intercept_task(task)


def _emit_loop_event(
    interceptor: AcademyInterceptor,
    runtime: Any,
    loop_name: str,
    event: str,
    task_id: str,
    group_id: str,
    started_at: float,
    tel: Any,
    error: BaseException | None = None,
) -> None:
    with _timed("loop_emit"):
        agent_type, agent_id = _agent_info(runtime)
        task: dict[str, Any] = {
            "task_id": task_id,
            "subtype": "academy_loop",
            "activity_id": loop_name,
            "group_id": group_id,
            "agent_id": agent_id,
            "custom_metadata": {
                "agent_type": agent_type,
                "loop_event": event,
            },
            "started_at": started_at,
            "ended_at": time.time(),
            "status": "ERROR" if error else "FINISHED",
            "stderr": str(error) if error else None,
        }
        tel_key = "telemetry_at_start" if event == "start" else "telemetry_at_end"
        if tel is not None:
            task[tel_key] = _tel_to_dict(tel)
        interceptor.intercept_task(task)


def _emit_lifecycle(interceptor: AcademyInterceptor, runtime: Any, event: str) -> None:
    with _timed("lifecycle_emit"):
        agent_type, agent_id = _agent_info(runtime)
        now = time.time()
        task: dict[str, Any] = {
            "subtype": "academy_lifecycle",
            "activity_id": event,
            "agent_id": agent_id,
            "custom_metadata": {"agent_type": agent_type},
            "started_at": now,
            "ended_at": now,
            "status": "FINISHED",
        }
        interceptor.intercept_task(task)


# ---------------------------------------------------------------------------
# LLM hook — each LLM call becomes a child TaskObject of its parent action
# ---------------------------------------------------------------------------


def _on_llm_call(payload: dict) -> None:
    interceptor = _ACTIVE_INTERCEPTOR
    if interceptor is None:
        return
    call_type = payload.get("type", "")
    if call_type not in _CAPTURE_LLM_TYPES:
        return
    with _timed("llm_hook"):
        _process_llm_call(interceptor, payload, call_type)


def record_llm_call(payload: dict) -> None:
    """
    Public API to record an LLM call into the active FlowCept provenance graph.

    Call this after any LLM invocation to capture it as a child TaskObject of
    the enclosing Academy @action.  The payload must include at minimum:

        type   : "chat_completion" | "parsed_json_result" |
                 "embed_result_local" | "embed_result_openai"
        model  : str  — model name requested
        text   : str  — response text (for chat_completion)
        usage  : dict — {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}

    No-ops if the plugin has not been started.
    """
    _on_llm_call(payload)


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
    reasoning_effort: str | None = None,  # "low" | "medium" | "high" for o1/o3 models
    response_format: dict | None = None,
    tools: list | None = None,
    tool_choice: str | dict | None = None,
    user: str | None = None,
    context: dict | None = None,
) -> str:
    """
    Make an OpenAI chat completion call and record it for FlowCept provenance.

    Captures all request parameters and response fields — including token usage
    breakdown (reasoning tokens, cached tokens), system fingerprint, model
    routing, finish reason, and tool calls — as a child TaskObject of the
    enclosing Academy @action.

    Parameters
    ----------
    prompt : str
        The user message.
    model : str
        OpenAI model name (e.g. "gpt-4o-mini", "o1-mini", "o3").
    system : str
        System prompt.
    temperature : float or None
        Sampling temperature. Set to None for reasoning models (o1/o3) that
        do not accept a temperature parameter.
    top_p : float or None
        Nucleus sampling probability.
    max_tokens : int or None
        Maximum tokens to generate (maps to max_completion_tokens for o-series).
    n : int
        Number of completions to generate.
    stop : list[str] or str or None
        Stop sequences.
    frequency_penalty : float
        Penalises repeated tokens by frequency.
    presence_penalty : float
        Penalises tokens already present in the context.
    seed : int or None
        Seed for deterministic sampling.
    reasoning_effort : str or None
        "low" | "medium" | "high" — controls thinking budget on o1/o3 models.
    response_format : dict or None
        E.g. {"type": "json_object"} for JSON mode.
    tools : list or None
        OpenAI function-calling tool definitions.
    tool_choice : str or dict or None
        Tool selection strategy.
    user : str or None
        End-user identifier for abuse monitoring.
    context : dict, optional
        Extra tags stored in the provenance record (e.g. {"agent": "SummaryAgent"}).

    Returns
    -------
    str
        The model's response text (first choice).
    """
    import openai as _openai
    import time as _time

    client = _openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]

    # Build request kwargs — omit None values to avoid API errors on
    # models that reject unsupported parameters (e.g. temperature for o1).
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

    # Detailed token breakdown (available on newer API versions)
    usage_dict: dict = {}
    if hasattr(usage, "prompt_tokens"):
        usage_dict["prompt_tokens"] = usage.prompt_tokens
    if hasattr(usage, "completion_tokens"):
        usage_dict["completion_tokens"] = usage.completion_tokens
    if hasattr(usage, "total_tokens"):
        usage_dict["total_tokens"] = usage.total_tokens
    # Reasoning tokens (o1/o3)
    if hasattr(usage, "completion_tokens_details") and usage.completion_tokens_details:
        ctd = usage.completion_tokens_details
        usage_dict["reasoning_tokens"] = getattr(ctd, "reasoning_tokens", None)
        usage_dict["accepted_prediction_tokens"] = getattr(ctd, "accepted_prediction_tokens", None)
        usage_dict["rejected_prediction_tokens"] = getattr(ctd, "rejected_prediction_tokens", None)
    # Cached prompt tokens
    if hasattr(usage, "prompt_tokens_details") and usage.prompt_tokens_details:
        ptd = usage.prompt_tokens_details
        usage_dict["cached_tokens"] = getattr(ptd, "cached_tokens", None)

    # Tool calls in the response
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
            # --- request ---
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
            # --- response ---
            "text": text,
            "finish_reason": choice.finish_reason,
            "tool_calls": tool_calls,
            "system_fingerprint": getattr(response, "system_fingerprint", None),
            "response_id": response.id,
            "created": response.created,
            "usage": usage_dict,
            "elapsed_s": elapsed,
            # --- provenance tags ---
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
    thinking: dict | None = None,  # {"type": "enabled", "budget_tokens": N} for extended thinking
    metadata: dict | None = None,
    context: dict | None = None,
) -> str:
    """
    Make an Anthropic (Claude) chat completion call and record it for FlowCept provenance.

    Captures all request parameters and response fields — including input/output
    token counts, cache usage, stop reason, thinking blocks, and tool use — as
    a child TaskObject of the enclosing Academy @action.

    Parameters
    ----------
    prompt : str
        The user message.
    model : str
        Anthropic model ID (e.g. "claude-haiku-4-5-20251001", "claude-opus-4-6").
    system : str
        System prompt.
    max_tokens : int
        Maximum tokens to generate (required by Anthropic API).
    temperature : float or None
        Sampling temperature (0–1). Set to None when using extended thinking.
    top_p : float or None
        Nucleus sampling probability.
    top_k : int or None
        Top-k sampling.
    stop_sequences : list[str] or None
        Custom stop sequences.
    tools : list or None
        Anthropic tool definitions.
    tool_choice : dict or None
        Tool selection strategy (e.g. {"type": "auto"}).
    thinking : dict or None
        Extended thinking config: {"type": "enabled", "budget_tokens": N}.
        When set, temperature must be 1.0 or None.
    metadata : dict or None
        End-user metadata for abuse monitoring (e.g. {"user_id": "..."}).
    context : dict, optional
        Extra tags stored in the provenance record (e.g. {"agent": "SummaryAgent"}).

    Returns
    -------
    str
        The model's response text (first text block).
    """
    import anthropic as _anthropic
    import time as _time

    client = _anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

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

    # Extract text and thinking blocks separately
    text = ""
    thinking_text = ""
    tool_uses = []
    for block in response.content:
        if block.type == "text":
            text += block.text
        elif block.type == "thinking":
            thinking_text += getattr(block, "thinking", "")
        elif block.type == "tool_use":
            tool_uses.append(
                {
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                }
            )

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
            # --- request ---
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
            # --- response ---
            "text": text,
            "thinking_text": thinking_text if thinking_text else None,
            "finish_reason": response.stop_reason,
            "stop_sequence": response.stop_sequence,
            "tool_uses": tool_uses if tool_uses else None,
            "response_id": response.id,
            "usage": usage_dict,
            "elapsed_s": elapsed,
            # --- provenance tags ---
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
        from flowcept.agents.academy.academy_plugin import FlowceptAnthropicClient

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


def _process_llm_call(interceptor: AcademyInterceptor, payload: dict, call_type: str) -> None:
    """Inner body of ``_on_llm_call``, extracted so ``_timed`` wraps everything."""
    now = time.time()
    ctx = payload.get("context") or {}
    model = payload.get("model", "unknown")
    model_used = payload.get("model_used", model)
    has_error = "error" in payload

    # parent_task_id: links this LLM call to the enclosing action or loop task
    parent_task_id = _current_action_task_id.get(None)

    # agent_id: always use the real Academy ID from the ContextVar (set before
    # task creation so all tasks inherit it).  ctx["agent"] is the class name
    # logged by application code — useful but not a reliable unique identifier.
    academy_agent_id = _current_academy_agent_id.get(None)
    ctx_agent_name = ctx.get("agent") or (
        _AGENT_ID_TO_TYPE.get(academy_agent_id, "unknown") if academy_agent_id else "unknown"
    )
    # Use the real Academy ID as the primary agent_id in provenance records.
    # Fall back to the class name only when the ID is genuinely unavailable.
    agent_id = academy_agent_id or ctx_agent_name

    # --- temperature ---
    temp_requested = payload.get("temperature_requested", payload.get("temperature"))
    temp_sent = payload.get("temperature_sent", payload.get("temperature"))
    temp_suppressed = payload.get("temperature_suppressed", False)

    if temp_requested is None:
        if temp_suppressed:
            temp_null_reason = "reasoning_model_does_not_accept_temperature"
        elif call_type in ("embed_result_local", "embed_result_openai"):
            temp_null_reason = "not_applicable_for_embeddings"
        else:
            temp_null_reason = "not_set"
    else:
        temp_null_reason = None

    # --- used (request / inputs) ---
    used: dict[str, Any] = {
        "model": model,
        "model_used": model_used,
        "call_type": ctx.get("call_type") or call_type,
        "temperature_requested": temp_requested,
        "temperature_sent": temp_sent,
        "temperature_suppressed": temp_suppressed,
        # Always store both the class-name agent and the Academy agent ID so
        # the record is self-contained for provenance queries.
        "agent_class": ctx_agent_name,
        "academy_agent_id": academy_agent_id,
    }
    if temp_null_reason is not None:
        used["temperature_null_reason"] = temp_null_reason
    if "messages" in payload:
        used["messages"] = payload["messages"]
    if "system_instructions" in payload:
        used["system_instructions"] = payload["system_instructions"]
    if "user_prompt" in payload:
        used["user_prompt"] = payload["user_prompt"]
    if "schema_hint" in payload:
        used["schema_hint"] = payload["schema_hint"]
    for k, v in ctx.items():
        used.setdefault(f"ctx_{k}", v)

    # --- generated (response / outputs) ---
    usage = payload.get("usage") or {}
    generated: dict[str, Any] = {
        "finish_reason": payload.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }

    if has_error:
        generated["error"] = str(payload["error"])

    elif call_type == "parsed_json_result":
        # _call_llm_json path: parsed_response contains the full structured output.
        parsed_resp = payload.get("parsed_response", {})
        generated["parsed_response"] = parsed_resp
        generated["fallback_used"] = payload.get("fallback_used", False)
        generated["raw_response_text"] = payload.get("raw_response_text", "")
        # Hoist all top-level fields from the parsed response so they are
        # directly queryable without unwrapping parsed_response.
        if isinstance(parsed_resp, dict):
            for k, v in parsed_resp.items():
                generated.setdefault(k, v)

    elif call_type == "chat_completion":
        response_text = payload.get("text", "")
        generated["response_text"] = response_text

        # Try to parse JSON embedded in the response text.
        parsed_inline: dict | None = None
        if response_text:
            s = response_text.strip()
            if s.startswith("```"):
                lines = s.splitlines()
                s = "\n".join(lines[1:-1]).strip()
            try:
                parsed_inline = _json.loads(s)
            except Exception:
                start = min(
                    (s.find("{") if s.find("{") != -1 else len(s)),
                    (s.find("[") if s.find("[") != -1 else len(s)),
                )
                end = max(s.rfind("}"), s.rfind("]"))
                if 0 <= start < end:
                    try:
                        parsed_inline = _json.loads(s[start : end + 1])
                    except Exception:
                        pass

        if isinstance(parsed_inline, dict):
            generated["parsed_response"] = parsed_inline
            # Hoist all top-level fields so they are directly queryable.
            for k, v in parsed_inline.items():
                generated.setdefault(k, v)

    elif call_type in ("embed_result_local", "embed_result_openai"):
        generated["num_vectors"] = payload.get("num_vectors")
        generated["embed_dim"] = payload.get("dim")

    task: dict[str, Any] = {
        "subtype": "llm_call",
        "activity_id": ctx.get("call_type") or call_type,
        # agent_id uses the real Academy ID when available
        "agent_id": agent_id,
        "custom_metadata": {
            "llm_call_type": call_type,
            "hyp_id": ctx.get("hyp_id"),
        },
        "started_at": now,
        "ended_at": now,
        "status": "ERROR" if has_error else "FINISHED",
        "used": used,
        "generated": generated,
    }
    if parent_task_id is not None:
        task["parent_task_id"] = parent_task_id

    interceptor.intercept_task(task)


# ---------------------------------------------------------------------------
# Public plugin class
# ---------------------------------------------------------------------------


class FlowceptAcademyPlugin:
    """
    Generic FlowCept provenance plugin for any Academy-based application.

    Patches Academy's Runtime at the class level (zero agent code changes required).
    Produces a full provenance graph: campaign → workflow → agent sub-workflows →
    action tasks → LLM child tasks, with CPU/memory telemetry and node enrichment.

    Parameters
    ----------
    config : dict, optional
        Plugin configuration keys:
          enabled (bool, default True)
          workflow_name (str, default "academy-workflow")
    llm_hook_register : callable, optional
        Called as llm_hook_register(_on_llm_call) on start to wire up LLM telemetry.
        Should match the signature used by your application's logging/hook module.
    llm_hook_unregister : callable, optional
        Called as llm_hook_unregister(_on_llm_call) on stop to remove the hook.
    """

    def __init__(
        self,
        config: dict | None = None,
        llm_hook_register: Any = None,
        llm_hook_unregister: Any = None,
    ) -> None:
        cfg = config or {}
        self._enabled: bool = cfg.get("enabled", False)
        self._workflow_name: str = cfg.get("workflow_name", "academy-workflow")
        self._campaign_id: str | None = cfg.get("campaign_id", None)
        self._perf_tracking: bool = cfg.get("performance_tracking", True)
        self._perf_csv: str | None = cfg.get("perf_csv", None)  # explicit override
        self._llm_hook_register = llm_hook_register
        self._llm_hook_unregister = llm_hook_unregister
        self._interceptor = AcademyInterceptor()
        self._started = False

    def start(self) -> "FlowceptAcademyPlugin":
        """Start provenance capture: install patches, hooks, and the interceptor."""
        if not self._enabled or self._started:
            return self
        global _ACTIVE_INTERCEPTOR, _PROV_STATS, _PERF_CSV_PATH
        try:
            _PROV_STATS = _ProvenanceStats() if self._perf_tracking else None
            self._interceptor.start(self._workflow_name, campaign_id=self._campaign_id)
            self._campaign_id = self._interceptor._campaign_id
            _ACTIVE_INTERCEPTOR = self._interceptor
            wf_id = self._interceptor._workflow_id
            _PERF_CSV_PATH = self._perf_csv or f"provenance_perf_{wf_id}.csv"
            _install_runtime_patches()
            _patch_process_pool_executor()
            if self._llm_hook_register is not None:
                self._llm_hook_register(_on_llm_call)
            self._started = True
            campaign_id = self._interceptor._campaign_id
            llm_status = "enabled" if self._llm_hook_register else "disabled (no hook provided)"
            print(
                f"[FlowceptAcademyPlugin] Started\n"
                f"  workflow_id : {wf_id}\n"
                f"  campaign_id : {campaign_id}\n"
                f"  Capturing   : agent lifecycle (sub-workflows), action dispatch "
                f"(telemetry + parent_task_id), loop events (group_id).\n"
                f"  LLM capture : {llm_status}",
                flush=True,
            )
        except Exception as e:
            print(
                f"[FlowceptAcademyPlugin] WARNING: failed to start — {e!r}. Continuing without provenance capture.",
                flush=True,
            )
            _log.exception("FlowceptAcademyPlugin start failed")
            self._enabled = False
        return self

    def stop(self) -> None:
        """Stop provenance capture: unregister hooks, remove patches, flush records."""
        if not self._started:
            return
        if self._llm_hook_unregister is not None:
            self._llm_hook_unregister(_on_llm_call)
        _uninstall_runtime_patches()
        _unpatch_process_pool_executor()
        try:
            self._interceptor.stop()
        except Exception as e:
            print(f"[FlowceptAcademyPlugin] Warning during stop: {e!r}", flush=True)
        self._started = False
        print("[FlowceptAcademyPlugin] Stopped.", flush=True)
        if _PROV_STATS is not None:
            print(
                "\n[FlowceptAcademyPlugin] Provenance overhead report:\n"
                + _PROV_STATS.summary()
                + "\n  (N = event count; Total/Mean/Min/Max in ms/µs respectively)\n",
                flush=True,
            )
            # Derive CSV path: explicit config > default based on workflow_id
            wf_id = self._interceptor._workflow_id
            csv_path = self._perf_csv or f"provenance_perf_{wf_id}.csv"
            try:
                _PROV_STATS.to_csv(csv_path, workflow_id=wf_id)
                print(
                    f"[FlowceptAcademyPlugin] Performance stats written to {csv_path}",
                    flush=True,
                )
            except Exception as e:
                print(
                    f"[FlowceptAcademyPlugin] Warning: could not write perf CSV — {e!r}",
                    flush=True,
                )


# Keep old name working
FlowceptPlugin = FlowceptAcademyPlugin


# ---------------------------------------------------------------------------
# Serialisation helper
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
