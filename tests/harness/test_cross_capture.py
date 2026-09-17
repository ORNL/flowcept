"""Tests for how the AI-harness capture and the agentic-framework plugins interoperate.

Three real join mechanisms exist between the two capture systems:

* a shared ``campaign_id``: the harness recorder stamps it on every buffer
  record (from ``Config.campaign_id`` / ``FLOWCEPT_HARNESS_CAMPAIGN_ID``), and
  the framework plugins stamp the same field on every emitted message, so the
  two record sets join on it downstream;
* framework -> harness linking: a harness-emitted ``task_id`` can be passed as
  ``_source_agent_id`` in a LangGraph initial state, and the LangGraph plugin
  stores it as ``custom_metadata.source_agent_id`` on its records;
* harness -> framework linking: a framework-emitted task/agent id reaches the
  harness recorder either as the ``flowcept_source_agent_id`` hook-payload key
  or via the ``FLOWCEPT_HARNESS_SOURCE_AGENT_ID`` environment variable (the
  payload key wins), and lands as ``source_agent_id`` on every turn, tool, and
  LLM-call task the harness emits. ``SessionTracer`` takes the same value as
  its ``source_agent_id`` argument.

Framework emission is captured in memory by replacing ``BaseInterceptor`` with
a fake (the pattern used by tests/agents/plugins), so no MQ, MongoDB, or
network access is needed. Harness emission goes to the per-test JSONL buffer.
"""

from __future__ import annotations

import json

import pytest

import flowcept.flowceptor.adapters.base_interceptor as base_interceptor_module
from flowcept.agents.harness import SessionTracer, ids, prov
from flowcept.agents.harness.config import load_config
from flowcept.agents.harness.emit import Emitter
from flowcept.agents.harness.vocab import AGENT_TOOL, AI_MODEL_INVOCATION
from flowcept.agents.langgraph.langgraph_plugin import FlowceptLangGraphPlugin

from .test_claude_code import fire

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")


class _CapturingInterceptor:
    """In-memory stand-in for BaseInterceptor that records all emissions."""

    instances: list = []

    def __init__(self, plugin_key=None, kind=None):
        """Record construction and initialize empty capture buffers."""
        self.kind = kind
        self.telemetry_capture = None
        self.stopped = False
        self.task_messages: list[dict] = []
        self.workflow_messages: list = []
        type(self).instances.append(self)

    def start(self, bundle_exec_id, check_safe_stops=True):
        """Mark the interceptor as started."""
        return self

    def stop(self, check_safe_stops=True):
        """Mark the interceptor as stopped."""
        self.stopped = True

    def send_workflow_message(self, workflow_obj):
        """Capture a WorkflowObject emission."""
        self.workflow_messages.append(workflow_obj)

    def intercept(self, task_dict):
        """Capture a task message emission."""
        self.task_messages.append(task_dict)


@pytest.fixture()
def captured(monkeypatch):
    """Patch BaseInterceptor with the capturing fake and return its instance list."""
    _CapturingInterceptor.instances = []
    monkeypatch.setattr(base_interceptor_module, "BaseInterceptor", _CapturingInterceptor)
    return _CapturingInterceptor.instances


def _build_graph():
    """Build a small local StateGraph of plain python-function nodes."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict, total=False):
        value: int
        _source_agent_id: str

    def _add_one(state):
        return {"value": state["value"] + 1}

    def _double(state):
        return {"value": state["value"] * 2}

    builder = StateGraph(_State)
    builder.add_node("add_one", _add_one)
    builder.add_node("double", _double)
    builder.add_edge(START, "add_one")
    builder.add_edge("add_one", "double")
    builder.add_edge("double", END)
    return builder.compile()


def _run_graph(captured, initial_state, campaign_id=None):
    """Invoke the local graph under a fresh LangGraph plugin; return its fake."""
    plugin_config = {"workflow_name": "cross-wf", "performance_tracking": False}
    if campaign_id:
        plugin_config["campaign_id"] = campaign_id
    plugin = FlowceptLangGraphPlugin(config=plugin_config)
    plugin.start()
    fake = captured[-1]
    try:
        graph = _build_graph()
        graph.invoke(initial_state, config={"callbacks": [plugin.callback_handler]})
    finally:
        plugin.stop()
    return fake


def _tasks(records, subtype=None):
    """Return the task records, optionally filtered by subtype."""
    return [r for r in records if r.get("type") == "task" and (subtype is None or r.get("subtype") == subtype)]


# -- source_agent_id on harness records ----------------------------------------


def test_task_record_carries_source_agent_id_into_the_buffer(config, buffer_records):
    """A harness task record built with a source agent id keeps it end-to-end.

    This exercises the record-builder/emitter level directly; the recorder,
    hook adapters, and tracer paths are covered by the tests below.
    """
    workflow_id = ids.workflow_id_for("sdk_agent", "link-run")
    record = prov.task_record(
        task_id=ids.tool_task_id(workflow_id, "t1"),
        workflow_id=workflow_id,
        activity_id="dispatch",
        subtype=AGENT_TOOL,
        source_agent_id="framework-agent-9",
    )
    Emitter(config, workflow_id).emit(record)

    (buffered,) = buffer_records()
    assert buffered["source_agent_id"] == "framework-agent-9"
    assert buffered["task_id"] == record["task_id"]


def test_recorder_emitted_tasks_have_no_source_agent_id_when_unset(config, buffer_records):
    """With no payload key, env var, or tracer argument, the field stays absent.

    None-valued keys are dropped by ``prov._clean``, so a harness run that was
    not given a source agent id never emits the field at all.
    """
    with SessionTracer("sdk_agent", "plain-run", config=config) as tracer:
        tracer.prompt("hello")
        call = tracer.tool_start("search", {"q": "x"})
        tracer.tool_end(call, tool_response={"hits": 1})
        tracer.turn_end("done")

    task_records = _tasks(buffer_records())
    assert task_records
    for record in task_records:
        assert "source_agent_id" not in record


def test_payload_key_sets_source_agent_id_on_harness_tasks(config, buffer_records):
    """The ``flowcept_source_agent_id`` hook-payload key lands on turn and tool tasks."""
    fire(config, "SessionStart", source="startup", model="claude-opus-5")
    fire(config, "UserPromptSubmit", prompt="go", prompt_id="p1")
    fire(config, "PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "ls"})
    fire(
        config,
        "PostToolUse",
        tool_name="Bash",
        tool_use_id="t1",
        tool_response={"ok": True},
        flowcept_source_agent_id="fw-task-42",
    )
    fire(config, "Stop", last_assistant_message="done", flowcept_source_agent_id="fw-task-42")
    fire(config, "SessionEnd", reason="clear")

    records = buffer_records()
    (tool,) = _tasks(records, AGENT_TOOL)
    (turn,) = _tasks(records, AI_MODEL_INVOCATION)
    assert tool["source_agent_id"] == "fw-task-42"
    assert turn["source_agent_id"] == "fw-task-42"


def test_env_source_agent_id_reaches_harness_tasks(monkeypatch, tmp_path):
    """FLOWCEPT_HARNESS_SOURCE_AGENT_ID flows through load_config onto every task."""
    monkeypatch.setenv("FLOWCEPT_HARNESS_SOURCE_AGENT_ID", "fw-env-7")
    monkeypatch.setenv("FLOWCEPT_HARNESS_HOME", str(tmp_path / "env-home"))
    env_config = load_config()
    assert env_config.source_agent_id == "fw-env-7"

    with SessionTracer("sdk_agent", "env-src-run", config=env_config) as tracer:
        tracer.prompt("hi")
        call = tracer.tool_start("search", {"q": "x"})
        tracer.tool_end(call, tool_response={"hits": 1})
        tracer.turn_end("done")

    records = []
    for path in sorted(env_config.buffers_dir.glob("*.jsonl")):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    task_records = _tasks(records)
    assert task_records
    for record in task_records:
        assert record["source_agent_id"] == "fw-env-7"


def test_payload_key_wins_over_env_source_agent_id(config, buffer_records):
    """When both are set, the payload key beats the env-configured value."""
    config.source_agent_id = "fw-from-env"  # what load_config would have set
    fire(config, "PreToolUse", tool_name="Bash", tool_use_id="t1", tool_input={"command": "ls"})
    fire(
        config,
        "PostToolUse",
        tool_name="Bash",
        tool_use_id="t1",
        tool_response={"ok": True},
        flowcept_source_agent_id="fw-from-payload",
    )
    fire(config, "Stop", last_assistant_message="done")

    records = buffer_records()
    (tool,) = _tasks(records, AGENT_TOOL)
    assert tool["source_agent_id"] == "fw-from-payload"
    # An event without the payload key still falls back to the env value.
    (turn,) = _tasks(records, AI_MODEL_INVOCATION)
    assert turn["source_agent_id"] == "fw-from-env"


# -- campaign_id as the cross-system join key -----------------------------------


def test_shared_campaign_id_joins_harness_and_langgraph_records(config, buffer_records, captured):
    """The same campaign_id on both captures lands on every record of each."""
    config.campaign_id = "camp-joint"
    with SessionTracer("sdk_agent", "camp-run", config=config) as tracer:
        tracer.prompt("plan")
        tracer.turn_end("planned")

    fake = _run_graph(captured, {"value": 1}, campaign_id="camp-joint")

    harness_records = buffer_records()
    assert harness_records
    for record in harness_records:
        if record.get("type") in ("task", "workflow", "agent"):
            assert record["campaign_id"] == "camp-joint"

    assert fake.workflow_messages[0].campaign_id == "camp-joint"
    assert fake.task_messages
    for task in fake.task_messages:
        assert task["campaign_id"] == "camp-joint"


def test_env_campaign_id_reaches_harness_records(monkeypatch, tmp_path):
    """FLOWCEPT_HARNESS_CAMPAIGN_ID flows through load_config onto the buffer."""
    monkeypatch.setenv("FLOWCEPT_HARNESS_CAMPAIGN_ID", "camp-env")
    monkeypatch.setenv("FLOWCEPT_HARNESS_HOME", str(tmp_path / "env-home"))
    env_config = load_config()
    assert env_config.campaign_id == "camp-env"

    with SessionTracer("sdk_agent", "env-run", config=env_config) as tracer:
        tracer.prompt("hi")
        tracer.turn_end("done")

    records = []
    for path in sorted(env_config.buffers_dir.glob("*.jsonl")):
        records.extend(json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    assert records
    assert {r["campaign_id"] for r in records if r.get("type") in ("task", "workflow")} == {"camp-env"}


# -- coexistence -----------------------------------------------------------------


def test_harness_and_langgraph_captures_coexist_in_one_process(config, buffer_records, captured):
    """Both captures running at once each produce intact, non-colliding records."""
    plugin = FlowceptLangGraphPlugin(config={"workflow_name": "co-wf", "performance_tracking": False})
    plugin.start()
    fake = captured[-1]
    try:
        with SessionTracer("sdk_agent", "co-run", config=config) as tracer:
            tracer.prompt("run the graph")
            graph = _build_graph()
            result = graph.invoke({"value": 3}, config={"callbacks": [plugin.callback_handler]})
            call = tracer.tool_start("invoke_graph", {"value": 3})
            tracer.tool_end(call, tool_response={"value": result["value"]})
            tracer.turn_end(f"graph returned {result['value']}")
    finally:
        plugin.stop()

    # The harness side is complete: buffer parses, and counts are as expected.
    harness_records = buffer_records()
    assert len(_tasks(harness_records, AI_MODEL_INVOCATION)) == 1
    (tool,) = _tasks(harness_records, AGENT_TOOL)
    assert tool["generated"]["value"] == 8
    session = [r for r in harness_records if r.get("type") == "workflow"][-1]
    assert session["status"] == "FINISHED"
    assert session["generated"] == {"turns": 1, "tool_calls": 1}

    # The framework side is complete too, and untouched by the harness capture.
    graph_tasks = [t for t in fake.task_messages if t["subtype"] == "langgraph_graph"]
    node_names = {t["activity_id"] for t in fake.task_messages if t["subtype"] == "langgraph_node"}
    assert len(graph_tasks) == 1
    assert {"add_one", "double"}.issubset(node_names)

    # No identifier from one system leaks into or collides with the other.
    harness_ids = {r.get("task_id") for r in _tasks(harness_records)}
    harness_ids |= {r["workflow_id"] for r in harness_records if r.get("type") == "workflow"}
    framework_ids = {t["task_id"] for t in fake.task_messages}
    framework_ids |= {w.workflow_id for w in fake.workflow_messages}
    assert not harness_ids & framework_ids


# -- framework -> harness linking -------------------------------------------------


def test_harness_tool_task_id_round_trips_through_a_langgraph_run(config, buffer_records, captured):
    """A real harness-emitted task_id passed as _source_agent_id lands on all records."""
    with SessionTracer("sdk_agent", "link-src", config=config) as tracer:
        call = tracer.tool_start("prepare_input", {"n": 1})
        tracer.tool_end(call, tool_response={"ready": True})

    (harness_tool,) = _tasks(buffer_records(), AGENT_TOOL)
    source_task_id = harness_tool["task_id"]

    fake = _run_graph(captured, {"value": 1, "_source_agent_id": source_task_id})

    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    assert graph_task["custom_metadata"]["source_agent_id"] == source_task_id
    for node_task in (t for t in fake.task_messages if t["subtype"] == "langgraph_node"):
        assert node_task["custom_metadata"]["source_agent_id"] == source_task_id


# -- harness -> framework linking -------------------------------------------------


def test_framework_task_id_round_trips_into_harness_records(config, buffer_records, captured):
    """A real framework-emitted task_id lands as source_agent_id on harness tasks."""
    fake = _run_graph(captured, {"value": 1})
    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    framework_task_id = graph_task["task_id"]

    with SessionTracer("sdk_agent", "link-back", config=config, source_agent_id=framework_task_id) as tracer:
        tracer.prompt("analyze the graph run")
        call = tracer.tool_start("inspect", {"target": "graph"})
        tracer.tool_end(call, tool_response={"ok": True})
        tracer.turn_end("done")

    records = buffer_records()
    (tool,) = _tasks(records, AGENT_TOOL)
    (turn,) = _tasks(records, AI_MODEL_INVOCATION)
    assert tool["source_agent_id"] == framework_task_id
    assert turn["source_agent_id"] == framework_task_id
