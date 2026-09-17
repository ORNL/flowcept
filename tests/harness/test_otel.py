"""Tests for OpenTelemetry ingest."""

from __future__ import annotations

import json

import pytest

from flowcept.agents.otel import otel_plugin as otel
from flowcept.agents.harness.vocab import AGENT_TOOL, AI_MODEL_INVOCATION, HARNESS_EVENT

CONVERSATION = "gen_ai.conversation.id"


def span(**attributes):
    """Build a minimal console-exporter-shaped span."""
    return {
        "name": attributes.pop("_name", "span"),
        "attributes": {CONVERSATION: "conv-1", **attributes},
        "start_time": 1_700_000_000_000_000_000,
        "end_time": 1_700_000_001_500_000_000,
        "context": {"span_id": "abc123"},
        "status": {"status_code": attributes.pop("_status", "OK")},
    }


def test_tool_span_becomes_a_tool_task(config, buffer_records):
    """A tool-execution span maps to an agent_tool task with parsed arguments."""
    assert otel.ingest_spans(
        [
            span(
                **{
                    "gen_ai.operation.name": "execute_tool",
                    "gen_ai.tool.name": "search_docs",
                    "gen_ai.tool.call.arguments": '{"query": "provenance"}',
                    "gen_ai.tool.call.result": '{"hits": 3}',
                }
            )
        ],
        config,
    )

    tool = next(r for r in buffer_records() if r.get("subtype") == AGENT_TOOL)
    assert tool["activity_id"] == "search_docs"
    # JSON-encoded attributes are parsed back into real fields.
    assert tool["used"]["query"] == "provenance"
    assert tool["generated"]["hits"] == 3
    assert tool["ended_at"] - tool["started_at"] == pytest.approx(1.5, abs=0.01)


def test_model_span_becomes_a_model_invocation(config, buffer_records):
    """A chat span maps to an ai_model_invocation task with model and usage."""
    otel.ingest_spans(
        [
            span(
                **{
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": "claude-opus-5",
                    "gen_ai.usage.input_tokens": 1200,
                    "gen_ai.usage.output_tokens": 340,
                }
            )
        ],
        config,
    )

    call = next(r for r in buffer_records() if r.get("subtype") == AI_MODEL_INVOCATION)
    assert call["custom_metadata"]["model"] == "claude-opus-5"
    assert call["custom_metadata"]["llm_usage"] == {"input_tokens": 1200, "output_tokens": 340}


def test_error_status_marks_the_tool_failed(config, buffer_records):
    """An ERROR span status becomes an errored task with its description as stderr."""
    bad = span(**{"gen_ai.tool.name": "deploy"})
    bad["status"] = {"status_code": "ERROR", "description": "permission denied"}
    otel.ingest_spans([bad], config)

    tool = next(r for r in buffer_records() if r.get("subtype") == AGENT_TOOL)
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "permission denied"


def test_non_genai_spans_are_ignored(config, buffer_records):
    """An HTTP client span is not provenance."""
    assert otel.ingest_spans([span(**{"http.method": "GET", "http.url": "https://x"})], config) == 0
    assert buffer_records() == []


def test_spans_without_a_conversation_id_are_ignored(config):
    """A span with no conversation id cannot be grouped and is skipped."""
    orphan = {"name": "tool", "attributes": {"gen_ai.tool.name": "x"}}
    assert otel.ingest_spans([orphan], config) == 0


def test_spans_group_into_one_session(config, buffer_records):
    """Spans sharing a conversation id land in one workflow."""
    otel.ingest_spans(
        [
            span(**{"gen_ai.operation.name": "chat", "gen_ai.request.model": "m"}),
            span(**{"gen_ai.tool.name": "read_file", "gen_ai.tool.call.id": "c1"}),
            span(**{"gen_ai.tool.name": "write_file", "gen_ai.tool.call.id": "c2"}),
        ],
        config,
    )
    workflows = [r for r in buffer_records() if r.get("type") == "workflow"]
    assert len(workflows) == 1
    assert len({r["workflow_id"] for r in buffer_records() if r.get("type") == "task"}) == 1


def test_mixed_gen_ai_system_does_not_split_the_session(config, buffer_records):
    """Spans of one conversation land in ONE workflow even when only some set `gen_ai.system`."""
    otel.ingest_spans(
        [
            span(**{CONVERSATION: "conv-mixed", "gen_ai.operation.name": "chat", "gen_ai.request.model": "m"}),
            span(
                **{
                    CONVERSATION: "conv-mixed",
                    "gen_ai.system": "openai",
                    "gen_ai.tool.name": "grep",
                    "gen_ai.tool.call.id": "c1",
                }
            ),
        ],
        config,
    )

    records = buffer_records()
    assert len([r for r in records if r.get("type") == "workflow"]) == 1
    assert len({r["workflow_id"] for r in records if r.get("type") == "task"}) == 1
    # The provider name is still recorded, as a one-time lifecycle event.
    notice = next(r for r in records if r.get("subtype") == HARNESS_EVENT)
    assert notice["used"] == {"trigger": "gen_ai.system", "message": "openai"}


def test_different_conversations_stay_separate_sessions(config, buffer_records):
    """Two conversation ids still yield two workflows."""
    otel.ingest_spans(
        [
            span(**{CONVERSATION: "conv-a", "gen_ai.tool.name": "alpha"}),
            span(**{CONVERSATION: "conv-b", "gen_ai.tool.name": "beta"}),
        ],
        config,
    )
    workflows = {r["workflow_id"] for r in buffer_records() if r.get("type") == "workflow"}
    assert len(workflows) == 2


def test_conflicting_gen_ai_system_first_value_wins(config, buffer_records):
    """Document the chosen policy: first-wins.

    The first non-empty `gen_ai.system` a conversation shows is the one
    recorded; later, different values neither re-record nor split the session.
    """
    otel.ingest_spans(
        [
            span(
                **{
                    CONVERSATION: "conv-conflict",
                    "gen_ai.system": "openai",
                    "gen_ai.tool.name": "t1",
                    "gen_ai.tool.call.id": "c1",
                }
            ),
            span(
                **{
                    CONVERSATION: "conv-conflict",
                    "gen_ai.system": "anthropic",
                    "gen_ai.tool.name": "t2",
                    "gen_ai.tool.call.id": "c2",
                }
            ),
        ],
        config,
    )

    records = buffer_records()
    assert len([r for r in records if r.get("type") == "workflow"]) == 1
    notices = [r for r in records if r.get("subtype") == HARNESS_EVENT]
    assert len(notices) == 1
    assert notices[0]["used"]["message"] == "openai"


def test_ingest_jsonl_file(config, tmp_path, buffer_records):
    """Spans written as JSON lines are ingested from disk."""
    path = tmp_path / "spans.jsonl"
    path.write_text(
        "\n".join(
            json.dumps(span(**{"gen_ai.tool.name": name, "gen_ai.tool.call.id": name})) for name in ("alpha", "beta")
        ),
        encoding="utf-8",
    )
    assert otel.ingest_file(path, config) == 2
    assert {r["activity_id"] for r in buffer_records() if r.get("subtype") == AGENT_TOOL} == {"alpha", "beta"}


def test_ingest_json_array_file(config, tmp_path):
    """Spans written as one JSON array are ingested from disk."""
    path = tmp_path / "spans.json"
    path.write_text(json.dumps([span(**{"gen_ai.tool.name": "alpha"})]), encoding="utf-8")
    assert otel.ingest_file(path, config) == 1


def test_ingest_otlp_envelope(config, buffer_records):
    """Collectors emit OTLP, whose attributes are a list of typed key-values."""
    envelope = {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "name": "tool",
                                "attributes": [
                                    {"key": CONVERSATION, "value": {"stringValue": "conv-9"}},
                                    {"key": "gen_ai.tool.name", "value": {"stringValue": "grep"}},
                                    {"key": "gen_ai.usage.input_tokens", "value": {"intValue": 42}},
                                ],
                                "startTimeUnixNano": 1_700_000_000_000_000_000,
                                "endTimeUnixNano": 1_700_000_000_500_000_000,
                            }
                        ]
                    }
                ]
            }
        ]
    }
    assert otel.ingest_spans(otel._flatten([envelope]), config) == 1
    assert next(r for r in buffer_records() if r.get("subtype") == AGENT_TOOL)["activity_id"] == "grep"


def test_exporter_records_live_spans(config, buffer_records):
    """Drive the exporter through a real tracer provider, not a stub."""
    pytest.importorskip("opentelemetry.sdk")
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(otel.FlowceptSpanExporter(config)))
    tracer = provider.get_tracer("test")

    with tracer.start_as_current_span("chat") as s:
        s.set_attribute(CONVERSATION, "live-1")
        s.set_attribute("gen_ai.operation.name", "chat")
        s.set_attribute("gen_ai.request.model", "claude-opus-5")
    with tracer.start_as_current_span("tool") as s:
        s.set_attribute(CONVERSATION, "live-1")
        s.set_attribute("gen_ai.tool.name", "run_tests")
    provider.shutdown()

    records = buffer_records()
    assert any(r.get("subtype") == AI_MODEL_INVOCATION for r in records)
    assert any(r.get("activity_id") == "run_tests" for r in records)


def test_exporter_survives_a_malformed_span(config):
    """A bad span must not take down the exporting process."""
    exporter = otel.FlowceptSpanExporter(config)
    exporter.export([object()])  # no attributes, no context, no status
