"""Unit tests for the FlowCept LangGraph provenance plugin.

Provenance emission is captured in memory by replacing ``BaseInterceptor``
with a fake that records every workflow and task message, so no MQ, MongoDB,
or network access is needed.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

import flowcept.agents.langgraph.langgraph_plugin as lg_module
import flowcept.flowceptor.adapters.base_interceptor as base_interceptor_module
from flowcept.agents.langgraph.langgraph_plugin import FlowceptLangGraphPlugin

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")


class _CapturingInterceptor:
    """In-memory stand-in for BaseInterceptor that records all emissions."""

    instances: list = []

    def __init__(self, plugin_key=None, kind=None):
        """Record construction and initialize empty capture buffers."""
        self.kind = kind
        self.telemetry_capture = None
        self.started = False
        self.stopped = False
        self.task_messages: list[dict] = []
        self.workflow_messages: list = []
        type(self).instances.append(self)

    def start(self, bundle_exec_id, check_safe_stops=True):
        """Mark the interceptor as started."""
        self.started = True
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


@pytest.fixture()
def started_plugin(captured):
    """Yield a started plugin plus the fake interceptor backing it."""
    plugin = FlowceptLangGraphPlugin(config={"workflow_name": "lg-test-wf", "performance_tracking": False})
    plugin.start()
    assert captured, "plugin.start() did not build an interceptor"
    yield plugin, captured[-1]
    plugin.stop()


def _build_graph(failing_node=False):
    """Build a small local StateGraph of plain python-function nodes."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict, total=False):
        value: int
        _source_agent_id: str

    def _add_one(state):
        return {"value": state["value"] + 1}

    def _double(state):
        if failing_node:
            raise ValueError("boom in node")
        return {"value": state["value"] * 2}

    builder = StateGraph(_State)
    builder.add_node("add_one", _add_one)
    builder.add_node("double", _double)
    builder.add_edge(START, "add_one")
    builder.add_edge("add_one", "double")
    builder.add_edge("double", END)
    return builder.compile()


class _Generation:
    """Minimal LangChain Generation stand-in."""

    def __init__(self, text):
        """Store the generated text."""
        self.text = text


class _LLMResult:
    """Minimal LangChain LLMResult stand-in."""

    def __init__(self, text, llm_output=None):
        """Store one generation and optional llm_output metadata."""
        self.generations = [[_Generation(text)]]
        self.llm_output = llm_output


# -- lifecycle ----------------------------------------------------------------


def test_start_emits_top_level_workflow_message(started_plugin):
    """start() sends one WorkflowObject carrying the configured workflow name."""
    _, fake = started_plugin
    assert len(fake.workflow_messages) == 1
    wf = fake.workflow_messages[0]
    assert wf.name == "lg-test-wf"
    assert wf.workflow_id is not None
    assert wf.campaign_id is not None


def test_start_respects_custom_campaign_id(captured):
    """A campaign_id passed in config is used verbatim on the workflow message."""
    plugin = FlowceptLangGraphPlugin(
        config={"workflow_name": "wf", "campaign_id": "camp-42", "performance_tracking": False}
    )
    plugin.start()
    try:
        assert captured[-1].workflow_messages[0].campaign_id == "camp-42"
    finally:
        plugin.stop()


def test_stop_stops_the_underlying_interceptor(started_plugin):
    """stop() flushes by stopping the wrapped interceptor exactly once."""
    plugin, fake = started_plugin
    plugin.stop()
    assert fake.stopped is True
    plugin.stop()  # second stop is a safe no-op


def test_disabled_plugin_emits_nothing(captured):
    """enabled=False disables capture entirely and never builds an interceptor."""
    plugin = FlowceptLangGraphPlugin(config={"enabled": False})
    plugin.start()
    assert captured == []
    with pytest.raises(RuntimeError):
        _ = plugin.callback_handler
    plugin.stop()


def test_callback_handler_raises_before_start(captured):
    """Accessing callback_handler before start() raises RuntimeError."""
    plugin = FlowceptLangGraphPlugin(config={"performance_tracking": False})
    with pytest.raises(RuntimeError):
        _ = plugin.callback_handler


def test_context_manager_starts_and_stops(captured):
    """The plugin works as a context manager, starting on enter and stopping on exit."""
    with FlowceptLangGraphPlugin(config={"workflow_name": "ctx-wf", "performance_tracking": False}) as plugin:
        assert plugin._started is True
        fake = captured[-1]
    assert plugin._started is False
    assert fake.stopped is True


# -- graph runs ---------------------------------------------------------------


def test_graph_invoke_emits_graph_and_node_tasks(started_plugin):
    """A local graph run yields one langgraph_graph task and one task per node."""
    plugin, fake = started_plugin
    graph = _build_graph()
    result = graph.invoke({"value": 3}, config={"callbacks": [plugin.callback_handler]})
    assert result["value"] == 8

    by_subtype = {}
    for task in fake.task_messages:
        by_subtype.setdefault(task["subtype"], []).append(task)
    graph_task = by_subtype["langgraph_graph"][0]
    node_names = {t["activity_id"] for t in by_subtype["langgraph_node"]}
    assert {"add_one", "double"}.issubset(node_names)
    assert graph_task["status"] == "FINISHED"
    assert graph_task["used"]["inputs"]["value"] == 3
    assert graph_task["generated"]["outputs"]["value"] == 8
    for task in fake.task_messages:
        assert task["workflow_id"] == fake.workflow_messages[0].workflow_id
        assert task["campaign_id"] == fake.workflow_messages[0].campaign_id
        assert task["status"] == "FINISHED"


def test_graph_invocation_emits_sub_workflow_linked_to_parent(started_plugin):
    """Each graph.invoke emits a sub-WorkflowObject pointing at the top workflow."""
    plugin, fake = started_plugin
    graph = _build_graph()
    graph.invoke({"value": 1}, config={"callbacks": [plugin.callback_handler]})

    top_wf, sub_wf = fake.workflow_messages[0], fake.workflow_messages[1]
    assert sub_wf.parent_workflow_id == top_wf.workflow_id
    assert sub_wf.custom_metadata["graph_name"] == sub_wf.name
    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    assert sub_wf.custom_metadata["group_id"] == graph_task["group_id"]


def test_node_tasks_share_group_id_and_link_to_graph_task(started_plugin):
    """All tasks of one invocation share a group_id; nodes parent to the graph task."""
    plugin, fake = started_plugin
    graph = _build_graph()
    graph.invoke({"value": 1}, config={"callbacks": [plugin.callback_handler]})

    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    node_tasks = [t for t in fake.task_messages if t["subtype"] == "langgraph_node"]
    assert node_tasks
    task_ids = {t["task_id"] for t in fake.task_messages}
    assert len(task_ids) == len(fake.task_messages)  # unique task ids
    for node_task in node_tasks:
        assert node_task["group_id"] == graph_task["group_id"]
        assert node_task["parent_task_id"] == graph_task["task_id"]


def test_node_error_is_recorded_as_failed_task(started_plugin):
    """A raising node produces ERROR-status tasks carrying the exception text."""
    plugin, fake = started_plugin
    graph = _build_graph(failing_node=True)
    with pytest.raises(ValueError, match="boom in node"):
        graph.invoke({"value": 1}, config={"callbacks": [plugin.callback_handler]})

    failed = [t for t in fake.task_messages if t["status"] == "ERROR"]
    assert failed
    assert any("boom in node" in t.get("stderr", "") for t in failed)


# -- LLM and tool callback events ----------------------------------------------


def test_llm_events_emit_llm_call_task(started_plugin):
    """on_llm_start/on_llm_end produce one llm_call task with prompts and tokens."""
    plugin, fake = started_plugin
    handler = plugin.callback_handler
    parent_id, run_id = uuid.uuid4(), uuid.uuid4()
    handler.on_chain_start(None, {"q": "hi"}, run_id=parent_id)
    handler.on_llm_start({"kwargs": {"model": "fake-model"}}, ["what is 2+2"], run_id=run_id, parent_run_id=parent_id)
    result = _LLMResult("4", {"token_usage": {"prompt_tokens": 12, "completion_tokens": 1, "total_tokens": 13}})
    handler.on_llm_end(result, run_id=run_id, parent_run_id=parent_id)
    handler.on_chain_end({"a": "4"}, run_id=parent_id)

    llm_task = next(t for t in fake.task_messages if t["subtype"] == "llm_call")
    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    assert llm_task["activity_id"] == "fake-model"
    assert llm_task["used"]["prompts"] == ["what is 2+2"]
    assert llm_task["generated"]["text"] == "4"
    assert llm_task["generated"]["total_tokens"] == 13
    assert llm_task["status"] == "FINISHED"
    assert llm_task["parent_task_id"] == graph_task["task_id"]
    assert llm_task["group_id"] == graph_task["group_id"]


def test_llm_error_emits_error_task(started_plugin):
    """on_llm_error records the llm_call task as ERROR with stderr set."""
    plugin, fake = started_plugin
    handler = plugin.callback_handler
    run_id = uuid.uuid4()
    handler.on_llm_start({"kwargs": {"model": "m"}}, ["p"], run_id=run_id)
    handler.on_llm_error(RuntimeError("rate limited"), run_id=run_id)

    llm_task = next(t for t in fake.task_messages if t["subtype"] == "llm_call")
    assert llm_task["status"] == "ERROR"
    assert "rate limited" in llm_task["stderr"]


def test_chat_model_events_emit_llm_call_task(started_plugin):
    """on_chat_model_start serializes message contents into the llm_call task."""
    plugin, fake = started_plugin
    handler = plugin.callback_handler
    run_id = uuid.uuid4()
    messages = [[SimpleNamespace(content="hello"), SimpleNamespace(content="world")]]
    handler.on_chat_model_start({"kwargs": {"model": "chat-model"}}, messages, run_id=run_id)
    handler.on_llm_end(_LLMResult("hi"), run_id=run_id)

    llm_task = next(t for t in fake.task_messages if t["subtype"] == "llm_call")
    assert llm_task["used"]["messages"] == [["hello", "world"]]
    assert llm_task["used"]["model"] == "chat-model"
    assert llm_task["generated"]["text"] == "hi"


def test_tool_events_emit_tool_call_task(started_plugin):
    """on_tool_start/on_tool_end produce one tool_call task with input and output."""
    plugin, fake = started_plugin
    handler = plugin.callback_handler
    parent_id, run_id = uuid.uuid4(), uuid.uuid4()
    handler.on_chain_start(None, {}, run_id=parent_id)
    handler.on_tool_start({"name": "get_weather"}, '{"city": "Paris"}', run_id=run_id, parent_run_id=parent_id)
    handler.on_tool_end("18C", run_id=run_id, parent_run_id=parent_id)
    handler.on_chain_end({}, run_id=parent_id)

    tool_task = next(t for t in fake.task_messages if t["subtype"] == "tool_call")
    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    assert tool_task["activity_id"] == "get_weather"
    assert tool_task["used"]["input"] == '{"city": "Paris"}'
    assert tool_task["generated"]["output"] == "18C"
    assert tool_task["status"] == "FINISHED"
    assert tool_task["parent_task_id"] == graph_task["task_id"]


def test_tool_error_emits_error_task(started_plugin):
    """on_tool_error records the tool_call task as ERROR with stderr set."""
    plugin, fake = started_plugin
    handler = plugin.callback_handler
    run_id = uuid.uuid4()
    handler.on_tool_start({"name": "deploy"}, "", run_id=run_id)
    handler.on_tool_error(RuntimeError("denied"), run_id=run_id)

    tool_task = next(t for t in fake.task_messages if t["subtype"] == "tool_call")
    assert tool_task["status"] == "ERROR"
    assert "denied" in tool_task["stderr"]


# -- record_llm_call public API -------------------------------------------------


def test_record_llm_call_routes_through_active_interceptor(started_plugin):
    """record_llm_call emits an llm_call task via the module-level interceptor."""
    _, fake = started_plugin
    lg_module.record_llm_call(
        {
            "type": "chat_completion",
            "model": "gpt-test",
            "text": "hello",
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    )
    llm_task = next(t for t in fake.task_messages if t["subtype"] == "llm_call")
    assert llm_task["activity_id"] == "gpt-test"
    assert llm_task["generated"]["text"] == "hello"
    assert llm_task["used"]["model"] == "gpt-test"
    assert llm_task["status"] == "FINISHED"


def test_record_llm_call_is_a_noop_when_plugin_stopped(captured):
    """After stop(), record_llm_call does not emit anything."""
    plugin = FlowceptLangGraphPlugin(config={"performance_tracking": False})
    plugin.start()
    fake = captured[-1]
    plugin.stop()
    emitted_before = len(fake.task_messages)
    lg_module.record_llm_call({"type": "chat_completion", "model": "m", "text": "t", "usage": {}})
    assert len(fake.task_messages) == emitted_before
