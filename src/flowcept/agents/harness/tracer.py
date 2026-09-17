"""A session you hold onto, for agents that run inside one process.

Hook adapters get a fresh process per event and rebuild their context from the
session file each time. An SDK does not: it has a run object, a callback
protocol, and a lifetime. :class:`SessionTracer` is the in-process counterpart —
it holds the sticky facts about the run (harness, model, cwd) so callbacks only
have to say what happened, not who it happened to.

    tracer = SessionTracer("my_agent", model="claude-opus-5")
    with tracer:
        tracer.prompt("summarize the repo")
        with tracer.tool("read_file", {"path": "README.md"}) as call:
            call.result({"bytes": 4096})
        tracer.turn_end(response="...", usage={"input_tokens": 900})

State still round-trips through the session file on every event, exactly as it
does for hooks. That costs a locked read-modify-write per callback, and buys
the thing that matters more: a run killed mid-flight leaves provenance that is
readable and correctly attributed rather than nothing at all.
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

from .config import Config
from .events import HarnessEvent
from .recorder import Recorder
from .vocab import EventKind


class SessionTracer:
    """Records one SDK-driven agent run as a Flowcept session.

    Parameters
    ----------
    harness:
        Identifies the SDK in the provenance, e.g. ``claude_agent_sdk``.
    session_id:
        The SDK's own conversation/thread id when it has one. All provenance
        ids derive from it, so passing the SDK's id is what lets a resumed run
        land in the same workflow. A random one is generated otherwise.
    model, cwd, project_dir:
        Sticky context replayed onto every event, so callbacks that only know
        about a tool call still produce fully attributed records.
    source_agent_id:
        A task or agent id from another capture system (e.g. a
        framework-emitted task that launched this run). Stamped as
        ``source_agent_id`` on every turn/tool/LLM task the run emits. Falls
        back to ``FLOWCEPT_HARNESS_SOURCE_AGENT_ID`` via the config.
    """

    def __init__(
        self,
        harness: str,
        session_id: str | None = None,
        *,
        config: Config | None = None,
        model: str | None = None,
        cwd: str | None = None,
        project_dir: str | None = None,
        source_agent_id: str | None = None,
        recorder: Recorder | None = None,
    ):
        self.harness = harness
        self.session_id = session_id or uuid.uuid4().hex
        self.recorder = recorder or Recorder(config)
        self.model = model
        self.cwd = cwd or _safe_cwd()
        self.project_dir = project_dir or os.environ.get("FLOWCEPT_HARNESS_PROJECT_DIR") or self.cwd
        self.source_agent_id = source_agent_id
        self._started = False
        self._ended = False
        # SDK callbacks can fire from a worker thread and from the main thread
        # in the same run; the session file's lock excludes other processes,
        # this excludes ourselves.
        self._lock = threading.Lock()

    # -- low level -----------------------------------------------------------

    def event(self, kind: str, **fields: Any) -> list[dict[str, Any]]:
        """Record one event, filling in the run's sticky context."""
        fields.setdefault("model", self.model)
        fields.setdefault("cwd", self.cwd)
        fields.setdefault("project_dir", self.project_dir)
        fields.setdefault("source_agent_id", self.source_agent_id)
        event = HarnessEvent(kind=kind, harness=self.harness, session_id=self.session_id, **fields)
        with self._lock:
            return self.recorder.record(event)

    # -- session lifecycle ---------------------------------------------------

    def start(self, *, source: str = "sdk", model: str | None = None, **fields: Any):
        """Open the session. Idempotent, and optional — any event opens it."""
        if model:
            self.model = model
        if self._started:
            return []
        self._started = True
        return self.event(EventKind.SESSION_START, source=source, **fields)

    def end(self, *, source: str = "completed", **fields: Any):
        """Close the session and write its final totals. Idempotent."""
        if self._ended:
            return []
        self._ended = True
        return self.event(EventKind.SESSION_END, source=source, **fields)

    def __enter__(self) -> SessionTracer:
        """Start the session and return the tracer."""
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """End the session, marking it as errored if an exception escaped."""
        self.end(source="error" if exc_type else "completed")
        return False

    # -- turns ---------------------------------------------------------------

    def prompt(self, text: str | None = None, *, prompt_id: str | None = None, **fields: Any):
        """Begin a turn. Any tool calls until :meth:`turn_end` hang off it."""
        return self.event(EventKind.PROMPT, prompt=text, prompt_id=prompt_id, **fields)

    def turn_end(
        self,
        response: str | None = None,
        *,
        usage: dict[str, Any] | None = None,
        **fields: Any,
    ):
        """Close the open turn with the assistant's answer."""
        return self.event(EventKind.TURN_END, response=response, usage=usage, **fields)

    def llm_call(
        self,
        *,
        model: str | None = None,
        prompt: str | None = None,
        response: str | None = None,
        usage: dict[str, Any] | None = None,
        call_id: str | None = None,
        started_at: float | None = None,
        error: str | None = None,
        **fields: Any,
    ):
        """Record a single model request, nested under the open turn.

        This is the granularity a hook cannot see. An SDK can, so SDK-captured
        sessions carry both: turn-level invocations and the calls inside them.
        """
        return self.event(
            EventKind.LLM_CALL,
            model=model or self.model,
            prompt=prompt,
            response=response,
            usage=usage,
            call_id=call_id,
            started_at=started_at,
            error=error,
            **fields,
        )

    # -- tools ---------------------------------------------------------------

    def tool_start(
        self,
        name: str,
        tool_input: Any = None,
        *,
        tool_use_id: str | None = None,
        agent_ref: str | None = None,
        **fields: Any,
    ) -> str:
        """Note that a tool is about to run; returns the id to close it with."""
        tool_use_id = tool_use_id or uuid.uuid4().hex
        self.event(
            EventKind.TOOL_PRE,
            tool_name=name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
            agent_ref=agent_ref,
            **fields,
        )
        return tool_use_id

    def tool_end(
        self,
        tool_use_id: str,
        *,
        name: str | None = None,
        tool_response: Any = None,
        error: str | None = None,
        agent_ref: str | None = None,
        started_at: float | None = None,
        **fields: Any,
    ):
        """Close a tool call opened by :meth:`tool_start`.

        Unpaired calls are fine: the recorder falls back to what this event
        carries, so a tool the SDK only reports on completion still lands.
        """
        return self.event(
            EventKind.TOOL_ERROR if error else EventKind.TOOL_POST,
            tool_name=name,
            tool_use_id=tool_use_id,
            tool_response=tool_response,
            error=error,
            agent_ref=agent_ref,
            started_at=started_at,
            **fields,
        )

    def tool(self, name: str, tool_input: Any = None, **fields: Any) -> _ToolCall:
        """Context manager form: records the call and any exception it raises.

        with tracer.tool("run_tests", {"suite": "unit"}) as call:
            call.result(run_tests())
        """
        return _ToolCall(self, name, tool_input, fields)

    # -- subagents -----------------------------------------------------------

    def subagent_start(
        self,
        agent_name: str,
        *,
        agent_ref: str | None = None,
        prompt: str | None = None,
        **fields: Any,
    ) -> str:
        """Open a nested workflow for a subagent; returns its ref."""
        agent_ref = agent_ref or uuid.uuid4().hex
        self.event(
            EventKind.SUBAGENT_START,
            agent_name=agent_name,
            agent_ref=agent_ref,
            prompt=prompt,
            **fields,
        )
        return agent_ref

    def subagent_stop(
        self,
        agent_ref: str,
        *,
        agent_name: str | None = None,
        response: str | None = None,
        error: str | None = None,
        **fields: Any,
    ):
        """Close a subagent's nested workflow."""
        return self.event(
            EventKind.SUBAGENT_STOP,
            agent_ref=agent_ref,
            agent_name=agent_name,
            response=response,
            error=error,
            **fields,
        )

    # -- lifecycle -----------------------------------------------------------

    def notify(self, message: str, **fields: Any):
        """Record a notification event carrying ``message``."""
        return self.event(EventKind.NOTIFICATION, message=message, **fields)

    def compact(self, *, source: str | None = None, **fields: Any):
        """Record a context-compaction event."""
        return self.event(EventKind.COMPACT, source=source, **fields)


class _ToolCall:
    """The context manager returned by :meth:`SessionTracer.tool`."""

    __slots__ = ("_fields", "_id", "_input", "_name", "_response", "_started", "_tracer")

    def __init__(self, tracer: SessionTracer, name: str, tool_input: Any, fields: dict[str, Any]):
        self._tracer = tracer
        self._name = name
        self._input = tool_input
        self._fields = fields
        self._id: str | None = None
        self._response: Any = None
        self._started = 0.0

    def __enter__(self) -> _ToolCall:
        self._started = time.time()
        self._id = self._tracer.tool_start(self._name, self._input, **self._fields)
        return self

    def result(self, value: Any) -> Any:
        """Record what the tool returned. Returns it, so it can wrap a call."""
        self._response = value
        return value

    def __exit__(self, exc_type, exc, tb) -> bool:
        self._tracer.tool_end(
            self._id or "",
            name=self._name,
            tool_response=self._response,
            error=f"{exc_type.__name__}: {exc}" if exc_type else None,
            started_at=self._started,
            agent_ref=self._fields.get("agent_ref"),
        )
        return False


def _safe_cwd() -> str | None:
    try:
        return os.getcwd()
    except OSError:
        # A deleted working directory is not a reason to lose the whole run.
        return None
