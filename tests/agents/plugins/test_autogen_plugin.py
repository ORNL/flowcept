"""Unit tests for the AutoGen provenance plugin.

These tests never touch MongoDB, Redis, an LLM API, or the network: FlowCept's
``BaseInterceptor`` is replaced by an in-memory fake that appends every
emitted workflow/task record to a plain list, and teams/model clients are
lightweight fakes shaped like the real AutoGen payloads (real
``TaskResult``/``TextMessage`` objects are used where the plugin type-checks).
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("autogen_agentchat")
pytest.importorskip("autogen_core")

from autogen_agentchat.agents import AssistantAgent  # noqa: E402
from autogen_agentchat.base import TaskResult  # noqa: E402
from autogen_agentchat.messages import TextMessage  # noqa: E402

import flowcept.flowceptor.adapters.base_interceptor as bi_mod  # noqa: E402
from flowcept.agents.autogen import autogen_plugin as agp  # noqa: E402
from flowcept.agents.autogen.autogen_plugin import (  # noqa: E402
    FlowceptAutoGenPlugin,
    FlowceptModelClient,
)


# -- capture fixture ----------------------------------------------------------


@pytest.fixture
def capture(monkeypatch):
    """Replace BaseInterceptor with an in-memory fake and return the record list."""
    state = {"records": [], "stop_calls": 0}

    class _FakeBaseInterceptor:
        """In-memory stand-in for FlowCept's BaseInterceptor (no MQ, no DB)."""

        def __init__(self, plugin_key=None, kind=None):
            self.kind = kind
            self.telemetry_capture = None

        def start(self, bundle_exec_id, check_safe_stops=True):
            """Pretend to start."""
            return self

        def stop(self, check_safe_stops=True):
            """Count flushes instead of talking to an MQ."""
            state["stop_calls"] += 1

        def intercept(self, obj):
            """Append a task record to the shared list."""
            state["records"].append(obj)

        def send_workflow_message(self, wf):
            """Append a workflow record to the shared list."""
            state["records"].append(wf.to_dict())

    monkeypatch.setattr(bi_mod, "BaseInterceptor", _FakeBaseInterceptor)
    yield state
    agp._ACTIVE_INTERCEPTOR = None
    agp._PROV_STATS = None


@pytest.fixture
def plugin(capture):
    """Return a started plugin wired to the in-memory capture fixture."""
    p = FlowceptAutoGenPlugin(config={"workflow_name": "autogen-test", "performance_tracking": False})
    p.start()
    yield p
    p.stop()


def _tasks(records, subtype=None):
    """Return captured task records, optionally filtered by subtype."""
    return [r for r in records if "subtype" in r and (subtype is None or r.get("subtype") == subtype)]


def _workflows(records):
    """Return captured workflow records."""
    return [r for r in records if r.get("type") == "workflow"]


# -- fakes --------------------------------------------------------------------


class FakeTeam:
    """Minimal team exposing run_stream(), shaped like an AutoGen group chat."""

    name = "fake_team"
    _participants: list = []

    def __init__(self, fail_after=None, llm_between_messages=False):
        self._fail_after = fail_after
        self._llm_between_messages = llm_between_messages

    async def run_stream(self, task, cancellation_token=None):
        """Yield two chat messages then a TaskResult, optionally failing midway."""
        yield TextMessage(source="user", content=task)
        if self._fail_after == 1:
            raise RuntimeError("team exploded")
        if self._llm_between_messages:
            agp.record_llm_call(
                {
                    "type": "chat_completion",
                    "model": "fake-model",
                    "text": "answer",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
                }
            )
        yield TextMessage(source="agent1", content="answer")
        yield TaskResult(messages=[], stop_reason="done")


class FakeChatCompletionClient:
    """Duck-typed AutoGen ChatCompletionClient returning a canned response."""

    model_info = {
        "vision": False,
        "function_calling": False,
        "json_output": False,
        "structured_output": False,
        "family": "fake",
    }
    model = "fake-model"

    async def create(self, messages, **kwargs):
        """Return a canned CreateResult-shaped object."""

        class _Usage:
            prompt_tokens = 3
            completion_tokens = 5

        class _Result:
            content = "hi there"
            finish_reason = "stop"
            usage = _Usage()

        return _Result()

    async def close(self):
        """No-op close."""


# -- lifecycle ----------------------------------------------------------------


def test_start_emits_top_level_workflow(plugin, capture):
    """Starting the plugin emits one WorkflowObject with the configured name."""
    wfs = _workflows(capture["records"])
    assert len(wfs) == 1
    assert wfs[0]["name"] == "autogen-test"
    assert wfs[0]["workflow_id"] == plugin._interceptor._workflow_id
    assert wfs[0]["campaign_id"] == plugin._interceptor._campaign_id


def test_disabled_plugin_does_not_start(capture):
    """With enabled=False in config, start() must be a no-op."""
    p = FlowceptAutoGenPlugin(config={"enabled": False})
    p.start()
    assert p._started is False
    assert capture["records"] == []


def test_context_manager_starts_and_stops(capture):
    """The plugin works as a context manager, flushing on exit."""
    with FlowceptAutoGenPlugin(config={"performance_tracking": False}) as p:
        assert p._started is True
        assert agp._ACTIVE_INTERCEPTOR is p._interceptor
    assert p._started is False
    assert capture["stop_calls"] == 1
    assert agp._ACTIVE_INTERCEPTOR is None


def test_stop_restores_assistant_agent_init(capture):
    """start() patches AssistantAgent.__init__ and stop() restores it."""
    original = AssistantAgent.__init__
    p = FlowceptAutoGenPlugin(config={"performance_tracking": False})
    p.start()
    assert AssistantAgent.__init__ is not original
    p.stop()
    assert AssistantAgent.__init__ is original


def test_intercept_task_fills_standard_fields(plugin, capture):
    """intercept_task adds ids and normalizes the status enum value."""
    plugin._interceptor.intercept_task({"activity_id": "a", "status": "ERROR"})
    task = capture["records"][-1]
    assert task["activity_id"] == "a"
    assert task["task_id"]
    assert task["workflow_id"] == plugin._interceptor._workflow_id
    assert task["campaign_id"] == plugin._interceptor._campaign_id
    assert task["status"] == "ERROR"
    assert "hostname" in task


# -- team runs ----------------------------------------------------------------


def test_run_team_emits_run_and_message_tasks(plugin, capture):
    """A team run yields one autogen_run task plus one task per message."""
    result = asyncio.run(plugin.run_team(FakeTeam(), "hello"))
    assert isinstance(result, TaskResult)
    assert result.stop_reason == "done"

    run = _tasks(capture["records"], "autogen_run")[0]
    msgs = _tasks(capture["records"], "autogen_message")
    assert run["activity_id"] == "fake_team"
    assert run["status"] == "FINISHED"
    assert run["used"] == {"task": "hello"}
    assert run["generated"]["stop_reason"] == "done"
    assert run["generated"]["message_count"] == 2
    assert [m["activity_id"] for m in msgs] == ["user", "agent1"]
    assert msgs[0]["generated"]["content"] == "hello"
    assert msgs[1]["generated"]["content"] == "answer"
    assert msgs[1]["generated"]["message_type"] == "TextMessage"


def test_message_tasks_share_group_id_and_parent(plugin, capture):
    """All messages of one run share group_id and are children of the run task."""
    asyncio.run(plugin.run_team(FakeTeam(), "hello"))
    run = _tasks(capture["records"], "autogen_run")[0]
    msgs = _tasks(capture["records"], "autogen_message")
    assert {m["group_id"] for m in msgs} == {run["group_id"]}
    assert {m["parent_task_id"] for m in msgs} == {run["task_id"]}
    # The run also emits a sub-workflow linked to the top-level workflow.
    sub_wfs = [w for w in _workflows(capture["records"]) if w.get("parent_workflow_id")]
    assert sub_wfs[0]["parent_workflow_id"] == plugin._interceptor._workflow_id
    assert sub_wfs[0]["custom_metadata"]["group_id"] == run["group_id"]


def test_run_team_records_cross_framework_source_agent_id(plugin, capture):
    """A source_agent_id from another framework lands in custom_metadata."""
    asyncio.run(plugin.run_team(FakeTeam(), "hello", source_agent_id="AgentId<beef>"))
    run = _tasks(capture["records"], "autogen_run")[0]
    assert run["custom_metadata"]["source_agent_id"] == "AgentId<beef>"


def test_run_team_failure_emits_error_run_record(plugin, capture):
    """A failure mid-stream re-raises and records the run task as ERROR."""
    with pytest.raises(RuntimeError, match="team exploded"):
        asyncio.run(plugin.run_team(FakeTeam(fail_after=1), "hello"))
    run = _tasks(capture["records"], "autogen_run")[0]
    assert run["status"] == "ERROR"
    assert "team exploded" in run["stderr"]
    # The message seen before the failure was still captured.
    assert len(_tasks(capture["records"], "autogen_message")) == 1


def test_run_team_without_start_runs_plain(capture):
    """An unstarted plugin still runs the team but emits no provenance."""
    p = FlowceptAutoGenPlugin(config={"enabled": False})
    result = asyncio.run(p.run_team(FakeTeam(), "hello"))
    assert isinstance(result, TaskResult)
    assert capture["records"] == []


def test_module_level_run_team_uses_active_interceptor(plugin, capture):
    """agp.run_team() picks up the interceptor started by the plugin."""
    result = asyncio.run(agp.run_team(FakeTeam(), "hello", team_name="named_run"))
    assert isinstance(result, TaskResult)
    run = _tasks(capture["records"], "autogen_run")[0]
    assert run["activity_id"] == "named_run"


# -- LLM call capture ---------------------------------------------------------


def test_record_llm_call_emits_llm_task(plugin, capture):
    """record_llm_call() builds an llm_call task with used/generated payloads."""
    agp.record_llm_call(
        {
            "type": "chat_completion",
            "model": "fake-model",
            "user_prompt": "q",
            "temperature": 0.1,
            "text": "a",
            "finish_reason": "stop",
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            "context": {"agent_name": "agent1"},
        }
    )
    llm = _tasks(capture["records"], "llm_call")[0]
    assert llm["activity_id"] == "fake-model"
    assert llm["status"] == "FINISHED"
    assert llm["used"]["user_prompt"] == "q"
    assert llm["used"]["temperature"] == 0.1
    assert llm["generated"]["text"] == "a"
    assert llm["generated"]["usage"]["total_tokens"] == 3
    assert llm["custom_metadata"]["agent_id"] == "agent1"


def test_record_llm_call_error_marks_task_failed(plugin, capture):
    """A payload containing 'error' produces an ERROR llm_call task."""
    agp.record_llm_call({"type": "chat_completion", "model": "m", "error": "rate limited"})
    llm = _tasks(capture["records"], "llm_call")[0]
    assert llm["status"] == "ERROR"
    assert llm["generated"]["error"] == "rate limited"


def test_record_llm_call_noop_when_plugin_not_started(capture):
    """record_llm_call() must not emit or raise when no plugin is active."""
    assert agp._ACTIVE_INTERCEPTOR is None
    agp.record_llm_call({"type": "chat_completion", "model": "m", "text": "x"})
    assert capture["records"] == []


def test_llm_call_inside_stream_links_to_message_task(plugin, capture):
    """An LLM call made mid-stream is a child of the current message task."""
    asyncio.run(plugin.run_team(FakeTeam(llm_between_messages=True), "hello"))
    first_msg = _tasks(capture["records"], "autogen_message")[0]
    llm = _tasks(capture["records"], "llm_call")[0]
    assert llm["parent_task_id"] == first_msg["task_id"]
    assert llm["custom_metadata"]["agent_id"] == first_msg["activity_id"]


def test_flowcept_model_client_records_usage(plugin, capture):
    """FlowceptModelClient.create() records model, agent, and token usage."""
    wrapped = FlowceptModelClient(FakeChatCompletionClient(), agent_name="worker")
    result = asyncio.run(wrapped.create([TextMessage(source="u", content="q")], temperature=0.2))
    assert result.content == "hi there"

    llm = _tasks(capture["records"], "llm_call")[0]
    assert llm["activity_id"] == "fake-model"
    assert llm["used"]["temperature"] == 0.2
    assert llm["generated"]["text"] == "hi there"
    assert llm["generated"]["usage"] == {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}
    assert llm["custom_metadata"]["agent_id"] == "worker"
    assert llm["custom_metadata"]["framework"] == "autogen"


def test_assistant_agent_model_client_auto_wrapped(plugin):
    """While the plugin runs, new AssistantAgents get a wrapped model client."""
    agent = AssistantAgent(name="a1", model_client=FakeChatCompletionClient())
    assert isinstance(agent._model_client, FlowceptModelClient)
