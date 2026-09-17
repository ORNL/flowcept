"""OpenAI Agents SDK wrapper.

The Agents SDK already traces itself — every run produces a trace of typed
spans — and lets you register extra processors for those spans. So capture is a
processor, not a wrapper: nothing about how you call the SDK changes.

    from flowcept.agents.openai_agents.openai_agents_plugin import install
    install()

    result = await Runner.run(agent, "fix the failing test")

How the SDK's span types map onto PROV-AGENT:

===================  ====================================================
trace                the session workflow, plus one turn spanning the run
``generation``       ``ai_model_invocation`` at call granularity
``response``         the same, for the Responses API
``function``         ``agent_tool``
``mcp_tools``        ``agent_tool``
``guardrail``        ``agent_tool`` (it runs, it passes or trips)
nested ``agent``     a subagent workflow — agent-as-tool
root ``agent``       the session itself; contributes its name, not a record
``handoff``          a lifecycle event on the session
===================  ====================================================

Duck-typed against the SDK: nothing here imports ``agents``, so the module
imports and tests without it.
"""

from __future__ import annotations

import datetime
from typing import Any

from flowcept.agents.harness.config import Config
from flowcept.agents.harness.tracer import SessionTracer

#: Span types recorded as tool executions.
TOOL_SPANS = frozenset({"function", "mcp_tools", "guardrail", "custom"})

#: Span types recorded as model invocations.
MODEL_SPANS = frozenset({"generation", "response"})


class FlowceptTraceProcessor:
    """An Agents SDK ``TracingProcessor`` that writes Flowcept provenance.

    Deliberately not subclassing the SDK's ``TracingProcessor``: doing so would
    make ``openai-agents`` a hard import, and the SDK duck-types processors.
    """

    def __init__(self, config: Config | None = None, *, harness: str = "openai_agents"):
        self.config = config
        self.harness = harness
        self._tracers: dict[str, SessionTracer] = {}
        #: span_id -> trace_id, so a span can find its session.
        self._traces: dict[str, str] = {}
        self._parents: dict[str, str | None] = {}
        #: span_id of agent spans that opened a subagent workflow.
        self._agents: dict[str, str] = {}

    # -- traces --------------------------------------------------------------

    def on_trace_start(self, trace: Any) -> None:
        """Open a session tracer for a new SDK trace."""
        trace_id = getattr(trace, "trace_id", None)
        if not trace_id:
            return
        # `group_id` is the SDK's conversation/thread id when the caller set
        # one. Preferring it means a multi-turn conversation is one session
        # rather than one session per run.
        session_id = getattr(trace, "group_id", None) or trace_id
        tracer = SessionTracer(self.harness, str(session_id), config=self.config)
        self._tracers[trace_id] = tracer
        tracer.start(source=getattr(trace, "name", None) or "run")
        tracer.prompt(None, prompt_id=trace_id)

    def on_trace_end(self, trace: Any) -> None:
        """Close the trace's session tracer and drop its span bookkeeping."""
        trace_id = getattr(trace, "trace_id", None)
        tracer = self._tracers.pop(trace_id, None)
        if tracer is None:
            return
        tracer.turn_end()
        # A grouped conversation gets another trace, and the session is reopened
        # by it; closing here is still right, because the closing record
        # supersedes rather than duplicates.
        tracer.end()
        # Drop the trace's spans. Computed before the loop, since the first
        # mapping cleared is the one the list is derived from.
        span_ids = [k for k, v in self._traces.items() if v == trace_id]
        for mapping in (self._traces, self._parents, self._agents):
            for span_id in span_ids:
                mapping.pop(span_id, None)

    # -- spans ---------------------------------------------------------------

    def on_span_start(self, span: Any) -> None:
        """Record the start of an SDK span in the owning session tracer."""
        tracer, data, span_type = self._resolve(span)
        if tracer is None:
            return

        span_id = getattr(span, "span_id", "")
        self._traces[span_id] = getattr(span, "trace_id", "")
        self._parents[span_id] = getattr(span, "parent_id", None)

        if span_type == "agent" and getattr(span, "parent_id", None):
            self._agents[span_id] = tracer.subagent_start(
                getattr(data, "name", None) or "agent",
                agent_ref=span_id,
            )
        elif span_type == "agent":
            # The root agent is the session; name it rather than nest it.
            model = getattr(data, "model", None)
            if isinstance(model, str):
                tracer.model = model
        elif span_type in TOOL_SPANS:
            tracer.tool_start(
                _span_name(data, span_type),
                _as_json(getattr(data, "input", None) or getattr(data, "data", None)),
                tool_use_id=span_id,
                agent_ref=self._owning_agent(span),
            )

    def on_span_end(self, span: Any) -> None:
        """Record the completion of an SDK span in the owning session tracer."""
        tracer, data, span_type = self._resolve(span)
        if tracer is None:
            return

        span_id = getattr(span, "span_id", "")
        error = _error_text(getattr(span, "error", None))
        started = _parse_time(getattr(span, "started_at", None))
        # The span already measured its own duration; without both ends the
        # record would be stamped with the time the callback happened to run.
        ended = _parse_time(getattr(span, "ended_at", None))
        when = {"timestamp": ended} if ended else {}

        if span_type == "agent":
            ref = self._agents.pop(span_id, None)
            if ref:
                tracer.subagent_stop(ref, response=_as_text(getattr(data, "output", None)), error=error, **when)
        elif span_type in TOOL_SPANS:
            tracer.tool_end(
                span_id,
                name=_span_name(data, span_type),
                tool_response=_as_json(getattr(data, "output", None)) if error is None else None,
                error=error or _guardrail_error(data),
                agent_ref=self._owning_agent(span),
                started_at=started,
                **when,
            )
        elif span_type in MODEL_SPANS:
            model, usage, output = _model_details(data)
            tracer.llm_call(
                model=model,
                prompt=_as_text(getattr(data, "input", None)),
                response=output,
                usage=usage,
                call_id=span_id,
                started_at=started,
                error=error,
                **when,
            )
        elif span_type == "handoff":
            source = getattr(data, "from_agent", None)
            target = getattr(data, "to_agent", None)
            tracer.notify(f"handoff: {source} -> {target}", source="handoff")

        self._traces.pop(span_id, None)
        self._parents.pop(span_id, None)

    # -- plumbing ------------------------------------------------------------

    def _resolve(self, span: Any) -> tuple[SessionTracer | None, Any, str | None]:
        tracer = self._tracers.get(getattr(span, "trace_id", None))
        data = getattr(span, "span_data", None)
        return tracer, data, getattr(data, "type", None)

    def _owning_agent(self, span: Any) -> str | None:
        """Return the nearest enclosing subagent, so its tools land in its workflow."""
        parent = getattr(span, "parent_id", None)
        seen = 0
        while parent and seen < 32:  # depth guard: the chain comes from outside
            if parent in self._agents:
                return self._agents[parent]
            parent = self._parents.get(parent)
            seen += 1
        return None

    def shutdown(self) -> None:
        """Close any session tracers still open when the SDK shuts down."""
        for trace_id in list(self._tracers):
            tracer = self._tracers.pop(trace_id)
            tracer.end(source="shutdown")

    def force_flush(self) -> None:
        """Do nothing; records are emitted as spans end."""
        return None


def install(config: Config | None = None, *, replace: bool = False) -> FlowceptTraceProcessor:
    """Register the processor with the Agents SDK's tracing provider.

    Adds to the existing processors by default, so the SDK's own trace export
    keeps working. Pass ``replace=True`` to make Flowcept the only consumer.
    """
    from agents import tracing

    processor = FlowceptTraceProcessor(config)
    if replace:
        tracing.set_trace_processors([processor])
    else:
        tracing.add_trace_processor(processor)
    return processor


# -- span-data readers --------------------------------------------------------


def _span_name(data: Any, span_type: str | None) -> str:
    name = getattr(data, "name", None)
    if isinstance(name, str) and name:
        return name
    return span_type or "tool"


def _guardrail_error(data: Any) -> str | None:
    """Return an error message for a tripped guardrail, which is a failed tool."""
    if getattr(data, "type", None) == "guardrail" and getattr(data, "triggered", False):
        return "guardrail triggered"
    return None


def _model_details(data: Any) -> tuple[str | None, dict[str, Any] | None, str | None]:
    """Pull model, usage, and output text from a generation or response span."""
    model = getattr(data, "model", None)
    usage = _as_dict(getattr(data, "usage", None))
    output = getattr(data, "output", None)

    response = getattr(data, "response", None)
    if response is not None:
        model = model or getattr(response, "model", None)
        usage = usage or _as_dict(getattr(response, "usage", None))
        output = output if output is not None else getattr(response, "output_text", None)

    return (model if isinstance(model, str) else None), usage, _as_text(output)


def _error_text(error: Any) -> str | None:
    if error is None:
        return None
    if isinstance(error, dict):
        message = error.get("message")
        data = error.get("data")
        return f"{message}: {data}" if message and data else (message or _as_text(data))
    return _as_text(error)


def _parse_time(value: Any) -> float | None:
    """Span timestamps are ISO-8601 strings."""
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None or isinstance(value, dict):
        return value
    for attribute in ("model_dump", "to_dict", "_asdict"):
        method = getattr(value, attribute, None)
        if callable(method):
            try:
                result = method()
            except Exception:
                continue
            if isinstance(result, dict):
                return result
    return getattr(value, "__dict__", None) or None


def _as_json(value: Any) -> Any:
    """Keep structure where there is any; ``used`` reads better with fields."""
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    return _as_dict(value) or repr(value)


def _as_text(value: Any) -> str | None:
    import json

    if value is None or isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=repr)
    except (TypeError, ValueError):
        return repr(value)
