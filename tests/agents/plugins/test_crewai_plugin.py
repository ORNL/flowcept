"""Unit tests for the FlowCept CrewAI provenance plugin.

Provenance emission is captured in memory by replacing ``BaseInterceptor``
with a fake that records every workflow and task message, so no MQ, MongoDB,
or network access is needed.  Because running a real Crew requires an LLM,
these tests drive the plugin's event-bus listener and LLM/tool hook surfaces
directly with synthetic events, mirroring the direct-handler-call style used
elsewhere in the test suite.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import flowcept.flowceptor.adapters.base_interceptor as base_interceptor_module
from flowcept.agents.crewai.crewai_plugin import FlowceptCrewAIPlugin

pytest.importorskip("crewai")


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
    plugin = FlowceptCrewAIPlugin(config={"workflow_name": "crew-test-wf", "performance_tracking": False})
    plugin.start()
    assert captured, "plugin.start() did not build an interceptor"
    yield plugin, captured[-1]
    plugin.stop()


def _run_crew_lifecycle(listener, crew_name="my-crew", inputs=None, fail=False):
    """Drive a full synthetic crew kickoff through the listener callbacks."""
    started = SimpleNamespace(crew_name=crew_name, inputs=inputs or {}, event_id="crew-evt-1")
    listener.on_crew_kickoff_started(None, started)
    if fail:
        failed = SimpleNamespace(event_id="crew-evt-2", started_event_id="crew-evt-1", error="kickoff exploded")
        listener.on_crew_kickoff_failed(None, failed)
    else:
        completed = SimpleNamespace(
            event_id="crew-evt-2", started_event_id="crew-evt-1", output="crew output", total_tokens=42
        )
        listener.on_crew_kickoff_completed(None, completed)


# -- lifecycle ----------------------------------------------------------------


def test_start_emits_top_level_workflow_message(started_plugin):
    """start() sends one WorkflowObject carrying the configured workflow name."""
    _, fake = started_plugin
    assert len(fake.workflow_messages) == 1
    wf = fake.workflow_messages[0]
    assert wf.name == "crew-test-wf"
    assert wf.workflow_id is not None
    assert wf.campaign_id is not None


def test_start_registers_llm_and_tool_hooks(started_plugin):
    """start() registers the plugin's global CrewAI LLM and tool hooks."""
    from crewai.hooks.llm_hooks import get_after_llm_call_hooks, get_before_llm_call_hooks
    from crewai.hooks.tool_hooks import get_after_tool_call_hooks, get_before_tool_call_hooks

    plugin, _ = started_plugin
    assert plugin._hooks_obj.before_llm_call in get_before_llm_call_hooks()
    assert plugin._hooks_obj.after_llm_call in get_after_llm_call_hooks()
    assert plugin._hooks_obj.before_tool_call in get_before_tool_call_hooks()
    assert plugin._hooks_obj.after_tool_call in get_after_tool_call_hooks()


def test_stop_unregisters_hooks_and_stops_interceptor(started_plugin):
    """stop() removes the global hooks and stops the wrapped interceptor."""
    from crewai.hooks.llm_hooks import get_before_llm_call_hooks
    from crewai.hooks.tool_hooks import get_before_tool_call_hooks

    plugin, fake = started_plugin
    plugin.stop()
    assert fake.stopped is True
    assert plugin._hooks_obj.before_llm_call not in get_before_llm_call_hooks()
    assert plugin._hooks_obj.before_tool_call not in get_before_tool_call_hooks()
    plugin.stop()  # second stop is a safe no-op


def test_disabled_plugin_emits_nothing(captured):
    """enabled=False disables capture entirely and never builds an interceptor."""
    plugin = FlowceptCrewAIPlugin(config={"enabled": False})
    plugin.start()
    assert captured == []
    plugin.stop()


def test_context_manager_starts_and_stops(captured):
    """The plugin works as a context manager, starting on enter and stopping on exit."""
    with FlowceptCrewAIPlugin(config={"workflow_name": "ctx-crew", "performance_tracking": False}) as plugin:
        assert plugin._started is True
        fake = captured[-1]
    assert plugin._started is False
    assert fake.stopped is True


def test_start_respects_custom_campaign_id(captured):
    """A campaign_id passed in config is used verbatim on the workflow message."""
    plugin = FlowceptCrewAIPlugin(
        config={"workflow_name": "wf", "campaign_id": "camp-7", "performance_tracking": False}
    )
    plugin.start()
    try:
        assert captured[-1].workflow_messages[0].campaign_id == "camp-7"
    finally:
        plugin.stop()


# -- crew kickoff -------------------------------------------------------------


def test_crew_kickoff_emits_crew_task_and_sub_workflow(started_plugin):
    """A kickoff start/complete pair yields one crewai_crew task and a sub-workflow."""
    plugin, fake = started_plugin
    _run_crew_lifecycle(plugin._listener_obj, inputs={"topic": "prov"})

    crew_task = next(t for t in fake.task_messages if t["subtype"] == "crewai_crew")
    assert crew_task["activity_id"] == "my-crew"
    assert crew_task["status"] == "FINISHED"
    assert crew_task["used"]["inputs"] == {"topic": "prov"}
    assert crew_task["generated"]["output"] == "crew output"
    assert crew_task["generated"]["total_tokens"] == 42
    assert crew_task["workflow_id"] == fake.workflow_messages[0].workflow_id
    assert crew_task["campaign_id"] == fake.workflow_messages[0].campaign_id

    top_wf, sub_wf = fake.workflow_messages[0], fake.workflow_messages[1]
    assert sub_wf.name == "my-crew"
    assert sub_wf.parent_workflow_id == top_wf.workflow_id
    assert sub_wf.custom_metadata["group_id"] == crew_task["group_id"]


def test_crew_kickoff_failure_recorded_as_error(started_plugin):
    """A kickoff failure event yields an ERROR crewai_crew task with stderr."""
    plugin, fake = started_plugin
    _run_crew_lifecycle(plugin._listener_obj, fail=True)

    crew_task = next(t for t in fake.task_messages if t["subtype"] == "crewai_crew")
    assert crew_task["status"] == "ERROR"
    assert "kickoff exploded" in crew_task["stderr"]


# -- task and agent lifecycle ---------------------------------------------------


def test_task_lifecycle_emits_crewai_task(started_plugin):
    """A task start/complete pair yields one crewai_task with metadata and output."""
    plugin, fake = started_plugin
    listener = plugin._listener_obj
    listener.on_crew_kickoff_started(None, SimpleNamespace(crew_name="c", inputs={}, event_id="ck-1"))
    listener.on_task_started(
        None,
        SimpleNamespace(event_id="tk-1", task_name="research", agent_role="researcher", context={"c": 1}, task=None),
    )
    listener.on_task_completed(None, SimpleNamespace(event_id="tk-2", started_event_id="tk-1", output="findings"))

    task = next(t for t in fake.task_messages if t["subtype"] == "crewai_task")
    assert task["activity_id"] == "research"
    assert task["status"] == "FINISHED"
    assert task["used"]["context"] == {"c": 1}
    assert task["generated"]["output"] == "findings"
    assert task["custom_metadata"]["task_name"] == "research"
    assert task["custom_metadata"]["agent_role"] == "researcher"
    crew_group = next(iter(listener._crew_group.values()))
    assert task["group_id"] == crew_group


def test_task_failure_recorded_as_error(started_plugin):
    """A task failure event yields an ERROR crewai_task with stderr."""
    plugin, fake = started_plugin
    listener = plugin._listener_obj
    listener.on_task_started(
        None, SimpleNamespace(event_id="tk-1", task_name="research", agent_role="r", context={}, task=None)
    )
    listener.on_task_failed(None, SimpleNamespace(event_id="tk-2", started_event_id="tk-1", error="task blew up"))

    task = next(t for t in fake.task_messages if t["subtype"] == "crewai_task")
    assert task["status"] == "ERROR"
    assert "task blew up" in task["stderr"]


def test_agent_execution_links_to_enclosing_task(started_plugin):
    """A crewai_agent task carries parent_task_id of the enclosing crewai_task."""
    plugin, fake = started_plugin
    listener = plugin._listener_obj
    listener.on_task_started(
        None, SimpleNamespace(event_id="tk-1", task_name="research", agent_role="researcher", context={}, task=None)
    )
    listener.on_agent_execution_started(
        None,
        SimpleNamespace(
            event_id="ag-1",
            agent=SimpleNamespace(role="researcher"),
            agent_role="researcher",
            task_prompt="find sources",
            tools=[SimpleNamespace(name="search")],
            started_event_id="tk-1",
            task_id=None,
        ),
    )
    listener.on_agent_execution_completed(
        None, SimpleNamespace(event_id="ag-2", started_event_id="ag-1", output="done")
    )
    listener.on_task_completed(None, SimpleNamespace(event_id="tk-2", started_event_id="tk-1", output="out"))

    agent_task = next(t for t in fake.task_messages if t["subtype"] == "crewai_agent")
    crew_task = next(t for t in fake.task_messages if t["subtype"] == "crewai_task")
    assert agent_task["activity_id"] == "researcher"
    assert agent_task["used"]["task_prompt"] == "find sources"
    assert agent_task["used"]["tools"] == ["search"]
    assert agent_task["generated"]["output"] == "done"
    assert agent_task["parent_task_id"] == crew_task["task_id"]


def test_agent_execution_error_recorded(started_plugin):
    """An agent execution error yields an ERROR crewai_agent task."""
    plugin, fake = started_plugin
    listener = plugin._listener_obj
    listener.on_agent_execution_started(
        None,
        SimpleNamespace(
            event_id="ag-1",
            agent=None,
            agent_role="researcher",
            task_prompt="x",
            tools=[],
            started_event_id=None,
            task_id=None,
        ),
    )
    listener.on_agent_execution_error(
        None, SimpleNamespace(event_id="ag-2", started_event_id="ag-1", error="agent crashed")
    )

    agent_task = next(t for t in fake.task_messages if t["subtype"] == "crewai_agent")
    assert agent_task["status"] == "ERROR"
    assert "agent crashed" in agent_task["stderr"]


# -- LLM and tool hooks ----------------------------------------------------------


def test_llm_hooks_emit_llm_call_with_agent_context(started_plugin):
    """The before/after LLM hooks emit one llm_call task linked to the agent task."""
    plugin, fake = started_plugin
    listener, hooks = plugin._listener_obj, plugin._hooks_obj
    listener.on_crew_kickoff_started(None, SimpleNamespace(crew_name="c", inputs={}, event_id="ck-1"))
    listener.on_agent_execution_started(
        None,
        SimpleNamespace(
            event_id="ag-1",
            agent=SimpleNamespace(role="writer"),
            agent_role="writer",
            task_prompt="write",
            tools=[],
            started_event_id=None,
            task_id=None,
        ),
    )
    executor = object()
    hooks.before_llm_call(
        SimpleNamespace(
            agent=SimpleNamespace(role="writer", goal="write well", backstory="b"),
            task=SimpleNamespace(description="write a poem", expected_output="poem"),
            llm=SimpleNamespace(model="fake-model"),
            messages=[{"role": "user", "content": "write a poem"}],
            iterations=2,
            executor=executor,
        )
    )
    hooks.after_llm_call(SimpleNamespace(executor=executor, response="roses are red"))

    llm_task = next(t for t in fake.task_messages if t["subtype"] == "llm_call")
    agent_fc_id = next(iter(listener._agent_fc_id.values()))
    assert llm_task["activity_id"] == "fake-model"
    assert llm_task["status"] == "FINISHED"
    assert llm_task["used"]["messages"] == [{"role": "user", "content": "write a poem"}]
    assert llm_task["used"]["agent_role"] == "writer"
    assert llm_task["used"]["task_description"] == "write a poem"
    assert llm_task["used"]["iterations"] == 2
    assert llm_task["generated"]["response"] == "roses are red"
    assert llm_task["parent_task_id"] == agent_fc_id
    assert llm_task["group_id"] == next(iter(listener._crew_group.values()))
    assert llm_task["custom_metadata"]["source"] == "llm_hook"


def test_tool_hooks_emit_tool_call_with_typed_input(started_plugin):
    """The before/after tool hooks emit one tool_call task with the typed input."""
    plugin, fake = started_plugin
    hooks = plugin._hooks_obj
    executor = object()
    hooks.before_tool_call(
        SimpleNamespace(
            tool_name="web_search",
            agent=SimpleNamespace(role="researcher"),
            task=SimpleNamespace(description="find sources"),
            tool_input={"query": "flowcept"},
            executor=executor,
        )
    )
    hooks.after_tool_call(SimpleNamespace(executor=executor, tool_result="found 3 results"))

    tool_task = next(t for t in fake.task_messages if t["subtype"] == "tool_call")
    assert tool_task["activity_id"] == "web_search"
    assert tool_task["status"] == "FINISHED"
    assert tool_task["used"]["input"] == {"query": "flowcept"}
    assert tool_task["used"]["agent_role"] == "researcher"
    assert tool_task["generated"]["output"] == "found 3 results"
    assert tool_task["custom_metadata"]["tool_name"] == "web_search"


def test_all_tasks_in_one_kickoff_share_group_id(started_plugin):
    """Crew, task, and agent records of one kickoff carry the same group_id."""
    plugin, fake = started_plugin
    listener = plugin._listener_obj
    listener.on_crew_kickoff_started(None, SimpleNamespace(crew_name="c", inputs={}, event_id="ck-1"))
    listener.on_task_started(
        None, SimpleNamespace(event_id="tk-1", task_name="t", agent_role="r", context={}, task=None)
    )
    listener.on_agent_execution_started(
        None,
        SimpleNamespace(
            event_id="ag-1",
            agent=None,
            agent_role="r",
            task_prompt="p",
            tools=[],
            started_event_id="tk-1",
            task_id=None,
        ),
    )
    listener.on_agent_execution_completed(None, SimpleNamespace(event_id="ag-2", started_event_id="ag-1", output="o"))
    listener.on_task_completed(None, SimpleNamespace(event_id="tk-2", started_event_id="tk-1", output="o"))
    listener.on_crew_kickoff_completed(
        None, SimpleNamespace(event_id="ck-2", started_event_id="ck-1", output="o", total_tokens=1)
    )

    group_ids = {t["group_id"] for t in fake.task_messages}
    assert len(fake.task_messages) == 3
    assert len(group_ids) == 1
    task_ids = {t["task_id"] for t in fake.task_messages}
    assert len(task_ids) == 3
