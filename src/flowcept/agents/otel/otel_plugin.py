"""OpenTelemetry ingest.

Many harnesses and agent frameworks already emit OTel spans and have no hook
system at all. Rather than ask them to add one, this adapter reads spans and
turns them into the same provenance everything else produces.

Two ways in:

*A span exporter* (:class:`FlowceptSpanExporter`) plugs into an in-process
tracer provider, so anything instrumented with OTel starts producing Flowcept
provenance with three lines of setup.

*A file reader* (:func:`ingest_file`) consumes spans already written as JSON,
which is what ``OTEL_TRACES_EXPORTER=console`` and most collectors produce.

The mapping follows the OTel GenAI semantic conventions, which name the
attributes this cares about: ``gen_ai.operation.name`` distinguishes a model
call from a tool call, ``gen_ai.tool.name`` names the tool, and
``gen_ai.conversation.id`` groups spans into a session. Non-GenAI spans are
ignored -- an HTTP client span is not provenance.

``gen_ai.system`` is optional and never affects grouping: session identity
derives from the conversation id alone, so spans with and without the
attribute land in one workflow. The first non-empty value a conversation
shows is recorded once as a lifecycle event; later or conflicting values are
ignored (first-wins).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from flowcept.agents.harness.config import Config, load_config
from flowcept.agents.harness.events import HarnessEvent
from flowcept.agents.harness.recorder import Recorder
from flowcept.agents.harness.vocab import EventKind

#: Session grouping, most specific first.
SESSION_KEYS = (
    "gen_ai.conversation.id",
    "gen_ai.session.id",
    "session.id",
    "session_id",
    "thread.id",
)

#: `gen_ai.operation.name` values that mean "the model was invoked".
MODEL_OPERATIONS = frozenset({"chat", "generate_content", "text_completion", "embeddings", "generate"})

#: ...and the ones that mean "a tool ran".
TOOL_OPERATIONS = frozenset({"execute_tool", "invoke_tool", "tool"})

#: The first non-empty ``gen_ai.system`` seen per conversation. The provider
#: name must never feed workflow identity (mixed presence would split one
#: conversation across workflows), so it is tracked here and recorded once as
#: a lifecycle event instead. First non-empty value wins.
_session_systems: dict[str, str] = {}


def _attr(attributes: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = attributes.get(key)
        if value is not None:
            return value
    return None


def _nanos_to_seconds(value: Any) -> float | None:
    """OTel timestamps are nanoseconds since the epoch."""
    if isinstance(value, (int, float)):
        return value / 1e9
    if isinstance(value, str):
        # Console exporters sometimes emit ISO-8601 instead.
        try:
            import datetime

            return datetime.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def span_to_event(span: dict[str, Any], *, harness: str = "otel") -> HarnessEvent | None:
    """Map one span dict onto a normalized event, or ``None`` to skip it.

    Accepts both the shape produced by the SDK's console exporter and the
    flattened shape most collectors emit.
    """
    attributes = span.get("attributes") or {}
    if not isinstance(attributes, dict):
        return None

    session_id = _attr(attributes, *SESSION_KEYS)
    if not session_id:
        # Without a conversation id spans cannot be grouped into a session, and
        # a per-span workflow would be noise rather than provenance.
        return None

    operation = _attr(attributes, "gen_ai.operation.name", "gen_ai.operation", "operation.name")
    tool_name = _attr(attributes, "gen_ai.tool.name", "tool.name")

    if operation in TOOL_OPERATIONS or tool_name:
        kind = EventKind.TOOL_POST
    elif operation in MODEL_OPERATIONS:
        kind = EventKind.LLM_CALL
    else:
        return None

    status = span.get("status") or {}
    status_code = status.get("status_code") if isinstance(status, dict) else status
    error = None
    if str(status_code).upper() in ("ERROR", "STATUS_CODE_ERROR"):
        error = (status.get("description") if isinstance(status, dict) else None) or "span reported an error"
        if kind == EventKind.TOOL_POST:
            kind = EventKind.TOOL_ERROR

    usage = {
        key: attributes[full]
        for key, full in (
            ("input_tokens", "gen_ai.usage.input_tokens"),
            ("output_tokens", "gen_ai.usage.output_tokens"),
            ("total_tokens", "gen_ai.usage.total_tokens"),
        )
        if full in attributes
    }

    started = _nanos_to_seconds(span.get("start_time") or span.get("startTimeUnixNano"))
    ended = _nanos_to_seconds(span.get("end_time") or span.get("endTimeUnixNano"))

    return HarnessEvent(
        kind=kind,
        # Deliberately NOT `gen_ai.system`: the harness partitions workflow
        # identity, and the provider attribute may be set on only some of a
        # conversation's spans. See `_provider_notice`.
        harness=harness,
        session_id=str(session_id),
        # The event carries the span's *end*; `started_at` preserves the
        # duration the span already measured.
        timestamp=ended or started or None,
        started_at=started,
        model=_attr(attributes, "gen_ai.request.model", "gen_ai.response.model", "llm.model_name"),
        prompt=_as_text(_attr(attributes, "gen_ai.prompt", "gen_ai.input.messages", "input.value")),
        response=_as_text(_attr(attributes, "gen_ai.completion", "gen_ai.output.messages", "output.value")),
        tool_name=tool_name or span.get("name"),
        tool_use_id=_attr(attributes, "gen_ai.tool.call.id", "tool.call.id") or _span_id(span),
        tool_input=_as_json(_attr(attributes, "gen_ai.tool.call.arguments", "tool.arguments", "input.value")),
        tool_response=_as_json(_attr(attributes, "gen_ai.tool.call.result", "tool.result", "output.value")),
        error=error,
        call_id=_attr(attributes, "gen_ai.response.id") or _span_id(span),
        usage=usage or None,
        agent_name=_attr(attributes, "gen_ai.agent.name", "agent.name"),
        agent_ref=_attr(attributes, "gen_ai.agent.id", "agent.id"),
    )


def _provider_notice(event: HarnessEvent, attributes: dict[str, Any]) -> HarnessEvent | None:
    """Build a one-time lifecycle event recording the session's ``gen_ai.system``.

    The provider name must not partition the session (that would split spans
    with and without the attribute across workflows), so it lands as a
    ``harness_event`` task in the conversation's workflow instead. The first
    non-empty value wins; later or conflicting values return ``None``.
    """
    system = _attr(attributes, "gen_ai.system", "service.name")
    if not system or event.session_id in _session_systems:
        return None
    _session_systems[event.session_id] = str(system)
    return HarnessEvent(
        kind=EventKind.NOTIFICATION,
        harness=event.harness,
        session_id=event.session_id,
        timestamp=event.timestamp,
        source="gen_ai.system",
        message=str(system),
        raw={"gen_ai.system": str(system)},
    )


def _span_id(span: dict[str, Any]) -> str | None:
    context = span.get("context") or span.get("spanContext") or {}
    if isinstance(context, dict):
        value = context.get("span_id") or context.get("spanId")
        if value:
            return str(value)
    value = span.get("span_id") or span.get("spanId")
    return str(value) if value else None


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return json.dumps(value, default=repr)


def _as_json(value: Any) -> Any:
    """Parse attribute values that carry JSON as a string.

    OTel attributes are scalars, so structured tool arguments arrive
    JSON-encoded. Recovering the structure means ``used`` holds real fields
    rather than one opaque string.
    """
    if isinstance(value, str):
        stripped = value.strip()
        if stripped[:1] in ("{", "["):
            try:
                return json.loads(stripped)
            except ValueError:
                return value
    return value


def ingest_spans(spans: Iterable[dict[str, Any]], config: Config | None = None) -> int:
    """Record every GenAI span in ``spans``. Returns how many were recorded."""
    config = config or load_config()
    recorder = Recorder(config)
    recorded = 0
    for span in spans:
        if not isinstance(span, dict):
            continue
        event = span_to_event(span)
        if event is None:
            continue
        if recorder.record(event):
            recorded += 1
        notice = _provider_notice(event, span.get("attributes") or {})
        if notice is not None:
            recorder.record(notice)
    return recorded


def ingest_file(path: str | Path, config: Config | None = None) -> int:
    """Record spans from a JSON or JSONL file of exported spans."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    spans: list[dict[str, Any]] = []
    stripped = text.lstrip()
    if stripped.startswith("["):
        loaded = json.loads(text)
        spans = [s for s in loaded if isinstance(s, dict)]
    else:
        # JSONL, or the console exporter's stream of pretty-printed objects.
        decoder = json.JSONDecoder()
        index = 0
        while index < len(text):
            while index < len(text) and text[index] in " \t\r\n":
                index += 1
            if index >= len(text):
                break
            try:
                obj, index = decoder.raw_decode(text, index)
            except ValueError:
                break
            if isinstance(obj, dict):
                spans.append(obj)

    return ingest_spans(_flatten(spans), config)


def _flatten(spans: Iterable[dict[str, Any]]) -> Iterable[dict[str, Any]]:
    """Yield individual spans from either bare spans or OTLP envelopes."""
    for item in spans:
        if "resourceSpans" in item or "resource_spans" in item:
            envelopes = item.get("resourceSpans") or item.get("resource_spans") or []
            for resource in envelopes:
                for scope in resource.get("scopeSpans") or resource.get("scope_spans") or []:
                    for span in scope.get("spans") or []:
                        yield _normalize_otlp(span)
        else:
            yield item


def _normalize_otlp(span: dict[str, Any]) -> dict[str, Any]:
    """Convert OTLP's list-of-key-value attributes into a plain dict."""
    attributes = span.get("attributes")
    if isinstance(attributes, list):
        flat: dict[str, Any] = {}
        for entry in attributes:
            key = entry.get("key")
            value = entry.get("value")
            if key is None or not isinstance(value, dict):
                continue
            # OTLP wraps each value in a type tag: {"stringValue": "..."}.
            for tag in ("stringValue", "intValue", "doubleValue", "boolValue"):
                if tag in value:
                    flat[key] = value[tag]
                    break
        span = {**span, "attributes": flat}
    return span


class FlowceptSpanExporter:
    """An OTel ``SpanExporter`` that records spans as Flowcept provenance.

    Usage::

        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from flowcept.agents.otel.otel_plugin import FlowceptSpanExporter

        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(FlowceptSpanExporter()))

    Deliberately not subclassing ``SpanExporter``: doing so would make
    ``opentelemetry-sdk`` a hard import of this module, and the class is
    duck-typed by the SDK anyway.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or load_config()
        self._recorder = Recorder(self.config)

    def export(self, spans) -> Any:
        """Convert each readable span to an event and record it."""
        for span in spans:
            try:
                data = self._readable_to_dict(span)
                event = span_to_event(data)
            except Exception:
                continue
            if event is not None:
                self._recorder.record(event)
                notice = _provider_notice(event, data.get("attributes") or {})
                if notice is not None:
                    self._recorder.record(notice)
        try:
            from opentelemetry.sdk.trace.export import SpanExportResult

            return SpanExportResult.SUCCESS
        except ImportError:
            return None

    @staticmethod
    def _readable_to_dict(span) -> dict[str, Any]:
        """Adapt a ``ReadableSpan`` to the dict shape :func:`span_to_event` reads."""
        context = span.get_span_context() if hasattr(span, "get_span_context") else None
        status = getattr(span, "status", None)
        return {
            "name": getattr(span, "name", None),
            "attributes": dict(getattr(span, "attributes", None) or {}),
            "start_time": getattr(span, "start_time", None),
            "end_time": getattr(span, "end_time", None),
            "context": {"span_id": format(context.span_id, "016x")} if context else {},
            "status": {
                "status_code": getattr(getattr(status, "status_code", None), "name", None),
                "description": getattr(status, "description", None),
            }
            if status is not None
            else {},
        }

    def shutdown(self) -> None:
        """Do nothing; the recorder needs no teardown."""
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        """Report success; records are written as spans are exported."""
        return True
