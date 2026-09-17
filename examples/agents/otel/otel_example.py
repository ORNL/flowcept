"""
OpenTelemetry GenAI span capture through FlowceptSpanExporter.

Anything already instrumented with OTel starts producing Flowcept provenance
with three lines of setup: build a ``TracerProvider``, add a
``SimpleSpanProcessor`` wrapping ``FlowceptSpanExporter``, and emit spans. This
example emits synthetic GenAI spans locally — a model call and a tool call —
so it runs fully offline, no collector and no API key.

Spans are read through the OTel GenAI semantic conventions:
``gen_ai.operation.name`` separates a model call from a tool call,
``gen_ai.tool.name`` names the tool, and ``gen_ai.conversation.id`` groups
spans into a session. Spans without a conversation id, and non-GenAI spans,
are ignored. Records land as PROV-AGENT provenance in a JSONL buffer under
``~/.flowcept/harness/buffers/``.

To ingest spans a collector already wrote instead (JSON/JSONL, including OTLP
envelopes), use ``flowcept.agents.otel.otel_plugin.ingest_file("spans.jsonl")``.

Run
---
    python examples/agents/otel/otel_example.py

Then inspect the capture:

    flowcept-harness sessions
    flowcept-harness show
    flowcept-harness report

Plugin configuration
--------------------
The harness plugins are configured with environment variables, not
settings.yaml (see src/flowcept/agents/harness/README.md for the full table):

    FLOWCEPT_HARNESS_ENABLED=1        # master switch (default)
    FLOWCEPT_HARNESS_ONLINE=0         # 1 publishes to a live Flowcept backend
    FLOWCEPT_HARNESS_REDACT=1         # redact credential-shaped values
"""

from __future__ import annotations

import sys
import uuid

from flowcept.agents.otel.otel_plugin import FlowceptSpanExporter

try:
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
except ImportError:
    print("ERROR: pip install opentelemetry-sdk  (or: pip install 'flowcept[harness_otel]')", file=sys.stderr)
    sys.exit(1)


def main():
    """Emit two synthetic GenAI spans through a real OTel tracer provider."""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(FlowceptSpanExporter()))
    tracer = provider.get_tracer("otel-example")

    session_id = f"otel-example-{uuid.uuid4().hex[:8]}"

    # A tool execution: gen_ai.operation.name "execute_tool" (or a
    # gen_ai.tool.name attribute) marks the span as an agent_tool task.
    with tracer.start_as_current_span("increment_counter") as span:
        span.set_attribute("gen_ai.operation.name", "execute_tool")
        span.set_attribute("gen_ai.conversation.id", session_id)
        span.set_attribute("gen_ai.tool.name", "increment_counter")
        span.set_attribute("gen_ai.tool.call.id", "call-1")
        span.set_attribute("gen_ai.tool.call.arguments", '{"steps": [1, 2, 3, 4, 5]}')
        span.set_attribute("gen_ai.tool.call.result", '{"total": 15}')

    # A model invocation: gen_ai.operation.name "chat" marks the span as an
    # ai_model_invocation task at call granularity.
    with tracer.start_as_current_span("chat gpt-4o-mini") as span:
        # `gen_ai.system` is optional: the first non-empty value a conversation
        # shows is recorded once as the session's provider (first-value-wins).
        # Spans with and without it land in the same workflow, so setting it on
        # only this span -- as here -- does not split the session.
        span.set_attribute("gen_ai.system", "openai")
        span.set_attribute("gen_ai.operation.name", "chat")
        span.set_attribute("gen_ai.conversation.id", session_id)
        span.set_attribute("gen_ai.request.model", "gpt-4o-mini")
        span.set_attribute("gen_ai.prompt", "What does the counter total 15 represent?")
        span.set_attribute("gen_ai.completion", "15 is the sum 1+2+3+4+5 — the 5th triangular number.")
        span.set_attribute("gen_ai.usage.input_tokens", 25)
        span.set_attribute("gen_ai.usage.output_tokens", 18)

    provider.shutdown()

    print(f"[example] Captured session {session_id!r} from two GenAI spans. Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
