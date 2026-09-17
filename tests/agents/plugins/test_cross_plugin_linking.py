"""Tests for cross-framework provenance linking through LangGraph.

As documented in the top-level README ("Cross-framework provenance linking"),
a LangGraph run accepts ``_source_agent_id`` in the initial graph state to
link its provenance to a source task from another framework.  The LangGraph
plugin stores the value as ``source_agent_id`` in ``custom_metadata`` of both
``langgraph_graph`` and ``langgraph_node`` records.

Emission is captured in memory by replacing ``BaseInterceptor`` with a fake,
so no MQ, MongoDB, or network access is needed.
"""

from __future__ import annotations

import pytest

import flowcept.flowceptor.adapters.base_interceptor as base_interceptor_module
from flowcept.agents.crewai.crewai_plugin import FlowceptCrewAIPlugin
from flowcept.agents.langgraph.langgraph_plugin import FlowceptLangGraphPlugin

pytest.importorskip("langgraph")
pytest.importorskip("langchain_core")
pytest.importorskip("crewai")


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


@pytest.fixture()
def langgraph_run(captured):
    """Return a runner that invokes a local graph and returns the fake interceptor."""

    def run(initial_state: dict):
        plugin = FlowceptLangGraphPlugin(config={"workflow_name": "link-wf", "performance_tracking": False})
        plugin.start()
        fake = captured[-1]
        try:
            graph = _build_graph()
            graph.invoke(initial_state, config={"callbacks": [plugin.callback_handler]})
        finally:
            plugin.stop()
        return fake

    return run


def _build_graph():
    """Build a small local StateGraph of plain python-function nodes."""
    from typing import TypedDict

    from langgraph.graph import END, START, StateGraph

    class _State(TypedDict, total=False):
        value: int
        _source_agent_id: str

    def _add_one(state):
        return {"value": state["value"] + 1}

    builder = StateGraph(_State)
    builder.add_node("add_one", _add_one)
    builder.add_edge(START, "add_one")
    builder.add_edge("add_one", END)
    return builder.compile()


def test_source_agent_id_is_stored_on_the_graph_task(langgraph_run):
    """The langgraph_graph record carries custom_metadata.source_agent_id."""
    fake = langgraph_run({"value": 1, "_source_agent_id": "source-task-123"})
    graph_task = next(t for t in fake.task_messages if t["subtype"] == "langgraph_graph")
    assert graph_task["custom_metadata"]["source_agent_id"] == "source-task-123"
    # The raw linking key also travels in the recorded graph inputs.
    assert graph_task["used"]["inputs"]["_source_agent_id"] == "source-task-123"


def test_source_agent_id_propagates_to_node_tasks(langgraph_run):
    """Every langgraph_node record of the run carries the same source_agent_id."""
    fake = langgraph_run({"value": 1, "_source_agent_id": "source-task-123"})
    node_tasks = [t for t in fake.task_messages if t["subtype"] == "langgraph_node"]
    assert node_tasks
    for node_task in node_tasks:
        assert node_task["custom_metadata"]["source_agent_id"] == "source-task-123"


def test_run_without_source_agent_id_has_no_linkage_field(langgraph_run):
    """Without _source_agent_id in the state, no record carries source_agent_id."""
    fake = langgraph_run({"value": 1})
    assert fake.task_messages
    for task in fake.task_messages:
        assert "source_agent_id" not in task.get("custom_metadata", {})


def test_langgraph_run_links_to_a_crewai_source_task(captured):
    """A CrewAI task_id passed as _source_agent_id ends up on the LangGraph records."""
    from types import SimpleNamespace

    crew_plugin = FlowceptCrewAIPlugin(config={"workflow_name": "crew-src", "performance_tracking": False})
    crew_plugin.start()
    crew_fake = captured[-1]
    try:
        listener = crew_plugin._listener_obj
        listener.on_task_started(
            None, SimpleNamespace(event_id="tk-1", task_name="research", agent_role="r", context={}, task=None)
        )
        listener.on_task_completed(None, SimpleNamespace(event_id="tk-2", started_event_id="tk-1", output="data"))
        source_task = next(t for t in crew_fake.task_messages if t["subtype"] == "crewai_task")
        source_task_id = source_task["task_id"]

        lg_plugin = FlowceptLangGraphPlugin(config={"workflow_name": "lg-target", "performance_tracking": False})
        lg_plugin.start()
        lg_fake = captured[-1]
        try:
            graph = _build_graph()
            graph.invoke(
                {"value": 1, "_source_agent_id": source_task_id},
                config={"callbacks": [lg_plugin.callback_handler]},
            )
        finally:
            lg_plugin.stop()
    finally:
        crew_plugin.stop()

    graph_task = next(t for t in lg_fake.task_messages if t["subtype"] == "langgraph_graph")
    assert graph_task["custom_metadata"]["source_agent_id"] == source_task_id
