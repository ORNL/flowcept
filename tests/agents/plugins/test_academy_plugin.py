"""Unit tests for the Academy provenance plugin.

These tests never touch MongoDB, Redis, or the network: the FlowCept
``BaseInterceptor`` is replaced by an in-memory fake that appends every
emitted workflow/task record to a plain list, while the plugin's own logic
(enrichment, patching of ``academy.runtime.Runtime``, ContextVars, LLM hook)
runs for real against a local Academy exchange.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

import pytest

pytest.importorskip("academy")

from academy.agent import Agent, action  # noqa: E402
from academy.exchange import LocalExchangeFactory  # noqa: E402
from academy.manager import Manager  # noqa: E402

import flowcept.flowceptor.adapters.base_interceptor as bi_mod  # noqa: E402
from flowcept.agents.academy import academy_plugin as ap  # noqa: E402
from flowcept.agents.academy.academy_plugin import FlowceptAcademyPlugin  # noqa: E402


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
            self.started = False

        def start(self, bundle_exec_id, check_safe_stops=True):
            """Mark the interceptor as started."""
            self.started = True
            return self

        def stop(self, check_safe_stops=True):
            """Count flushes instead of talking to an MQ."""
            state["stop_calls"] += 1
            self.started = False

        def intercept(self, obj):
            """Append a task record to the shared list."""
            state["records"].append(obj)

        def send_workflow_message(self, wf):
            """Append a workflow record to the shared list."""
            state["records"].append(wf.to_dict())

    monkeypatch.setattr(bi_mod, "BaseInterceptor", _FakeBaseInterceptor)
    yield state
    ap._ACTIVE_INTERCEPTOR = None


@pytest.fixture
def plugin(capture):
    """Return a started plugin wired to the in-memory capture fixture."""
    p = FlowceptAcademyPlugin(config={"enabled": True, "workflow_name": "academy-test", "performance_tracking": False})
    p.start()
    yield p
    p.stop()


def _tasks(records, subtype=None):
    """Return captured task records, optionally filtered by subtype."""
    return [r for r in records if r.get("type") == "task" and (subtype is None or r.get("subtype") == subtype)]


def _workflows(records):
    """Return captured workflow records."""
    return [r for r in records if r.get("type") == "workflow"]


# -- test agent ---------------------------------------------------------------


class EchoAgent(Agent):
    """Minimal Academy agent exercising success, failure, and ContextVars."""

    @action
    async def double(self, n: int) -> int:
        """Return twice the input."""
        return 2 * n

    @action
    async def boom(self) -> None:
        """Raise ValueError to exercise the error path."""
        raise ValueError("nope")

    @action
    async def whoami(self) -> tuple:
        """Return the cross-framework linking ContextVar values."""
        return (ap._current_action_task_id.get(), ap._current_academy_agent_id.get())

    @action
    async def call_llm(self) -> None:
        """Record a synthetic LLM call from inside an action."""
        ap.record_llm_call(
            {
                "type": "chat_completion",
                "model": "fake-model",
                "text": '{"score": 5}',
                "finish_reason": "stop",
                "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
                "context": {"call_type": "scoring"},
            }
        )


def _run_agent(script):
    """Launch one EchoAgent on a local exchange and run *script(handle)*."""

    async def main():
        factory = LocalExchangeFactory()
        executor = ThreadPoolExecutor(max_workers=2)
        async with await Manager.from_exchange_factory(factory=factory, executors=executor) as manager:
            handle = await manager.launch(EchoAgent)
            return await script(handle)

    return asyncio.run(main())


# -- lifecycle ----------------------------------------------------------------


def test_plugin_is_disabled_by_default(capture):
    """Without enabled=True in config, start() must be a no-op."""
    p = FlowceptAcademyPlugin(config={"workflow_name": "x"})
    p.start()
    assert p._started is False
    assert capture["records"] == []


def test_start_emits_top_level_workflow(plugin, capture):
    """Starting the plugin emits one WorkflowObject with the configured name."""
    wfs = _workflows(capture["records"])
    assert len(wfs) == 1
    assert wfs[0]["name"] == "academy-test"
    assert wfs[0]["workflow_id"] == plugin._interceptor._workflow_id
    assert wfs[0]["campaign_id"] == plugin._interceptor._campaign_id


def test_start_uses_configured_campaign_id(capture):
    """An explicit campaign_id in config is propagated to every record."""
    p = FlowceptAcademyPlugin(config={"enabled": True, "campaign_id": "camp-42", "performance_tracking": False})
    p.start()
    try:
        p._interceptor.intercept_task({"activity_id": "a"})
        assert _workflows(capture["records"])[0]["campaign_id"] == "camp-42"
        assert _tasks(capture["records"])[0]["campaign_id"] == "camp-42"
    finally:
        p.stop()


def test_start_registers_llm_hook_and_stop_unregisters(capture):
    """The LLM hook register/unregister callables receive the plugin's hook."""
    registered, unregistered = [], []
    p = FlowceptAcademyPlugin(
        config={"enabled": True, "performance_tracking": False},
        llm_hook_register=registered.append,
        llm_hook_unregister=unregistered.append,
    )
    p.start()
    p.stop()
    assert registered == [ap._on_llm_call]
    assert unregistered == [ap._on_llm_call]


def test_stop_flushes_interceptor_and_clears_active_state(plugin, capture):
    """stop() flushes the interceptor and deactivates the module-level state."""
    plugin.stop()
    assert capture["stop_calls"] == 1
    assert plugin._started is False
    assert ap._ACTIVE_INTERCEPTOR is None


def test_stop_restores_process_pool_executor(capture):
    """start() patches ProcessPoolExecutor.__init__ and stop() restores it."""
    original = ProcessPoolExecutor.__init__
    p = FlowceptAcademyPlugin(config={"enabled": True, "performance_tracking": False})
    p.start()
    assert ProcessPoolExecutor.__init__ is not original
    p.stop()
    assert ProcessPoolExecutor.__init__ is original


# -- interceptor enrichment ---------------------------------------------------


def test_intercept_task_fills_standard_fields(plugin, capture):
    """intercept_task adds type, ids, and normalizes the status enum value."""
    plugin._interceptor.intercept_task({"activity_id": "my_act", "status": "FINISHED"})
    task = _tasks(capture["records"])[0]
    assert task["type"] == "task"
    assert task["task_id"]
    assert task["workflow_id"] == plugin._interceptor._workflow_id
    assert task["campaign_id"] == plugin._interceptor._campaign_id
    assert task["status"] == "FINISHED"
    # enrich_task_dict adds host identity fields
    assert "hostname" in task


def test_intercept_task_normalizes_unknown_status(plugin, capture):
    """An unrecognized status string falls back to FINISHED."""
    plugin._interceptor.intercept_task({"activity_id": "a", "status": "banana"})
    assert _tasks(capture["records"])[0]["status"] == "FINISHED"


# -- real Academy runs --------------------------------------------------------


def test_action_run_emits_finished_task(plugin, capture):
    """A successful @action produces an academy_action task with used/generated."""

    async def script(handle):
        return await handle.double(21)

    assert _run_agent(script) == 42
    actions = [t for t in _tasks(capture["records"], "academy_action") if t["activity_id"] == "double"]
    assert len(actions) == 1
    task = actions[0]
    assert task["status"] == "FINISHED"
    assert task["used"]["args"] == [21]
    assert task["generated"] == 42
    assert task["ended_at"] >= task["started_at"]
    assert task["custom_metadata"]["agent_type"] == "EchoAgent"
    assert task["custom_metadata"]["cross_agent_call"] is False


def test_action_failure_emits_error_task(plugin, capture):
    """A raising @action produces a task with status ERROR and the stderr text."""

    async def script(handle):
        with pytest.raises(Exception):
            await handle.boom()

    _run_agent(script)
    task = [t for t in _tasks(capture["records"], "academy_action") if t["activity_id"] == "boom"][0]
    assert task["status"] == "ERROR"
    assert "nope" in task["stderr"]
    assert task["generated"] is None


def test_agent_lifecycle_records_and_sub_workflow(plugin, capture):
    """Agent startup/shutdown emit lifecycle tasks plus a linked sub-workflow."""

    async def script(handle):
        return await handle.double(1)

    _run_agent(script)
    lifecycle = _tasks(capture["records"], "academy_lifecycle")
    events = [t["activity_id"] for t in lifecycle]
    assert "agent_startup" in events
    assert "agent_shutdown" in events

    top_wf_id = plugin._interceptor._workflow_id
    sub_wfs = [w for w in _workflows(capture["records"]) if w.get("parent_workflow_id")]
    assert len(sub_wfs) == 1
    assert sub_wfs[0]["parent_workflow_id"] == top_wf_id
    assert sub_wfs[0]["custom_metadata"]["agent_type"] == "EchoAgent"


def test_contextvars_expose_action_task_id_and_agent_id(plugin, capture):
    """Inside an @action, the cross-framework linking ContextVars are set."""

    async def script(handle):
        return await handle.whoami()

    action_task_id, academy_agent_id = _run_agent(script)
    assert action_task_id is not None
    assert academy_agent_id is not None and academy_agent_id.startswith("AgentId")

    task = [t for t in _tasks(capture["records"], "academy_action") if t["activity_id"] == "whoami"][0]
    assert task["task_id"] == action_task_id
    assert task["agent_id"] == academy_agent_id
    # Outside any action, the ContextVars are unset in this context.
    assert ap._current_action_task_id.get() is None


def test_llm_call_inside_action_links_parent_task(plugin, capture):
    """record_llm_call() inside an @action becomes a child llm_call task."""

    async def script(handle):
        return await handle.call_llm()

    _run_agent(script)
    action_task = [t for t in _tasks(capture["records"], "academy_action") if t["activity_id"] == "call_llm"][0]
    llm = _tasks(capture["records"], "llm_call")[0]
    assert llm["parent_task_id"] == action_task["task_id"]
    assert llm["activity_id"] == "scoring"
    assert llm["agent_id"] == action_task["agent_id"]
    assert llm["used"]["model"] == "fake-model"
    assert llm["generated"]["total_tokens"] == 7
    # JSON embedded in the response text is parsed and hoisted for queries.
    assert llm["generated"]["parsed_response"] == {"score": 5}
    assert llm["generated"]["score"] == 5


def test_record_llm_call_noop_when_plugin_not_started(capture):
    """record_llm_call() must not emit or raise when no plugin is active."""
    assert ap._ACTIVE_INTERCEPTOR is None
    ap.record_llm_call({"type": "chat_completion", "model": "m", "text": "x"})
    assert capture["records"] == []


def test_llm_call_error_payload_marks_task_failed(plugin, capture):
    """An LLM payload containing 'error' produces an ERROR llm_call task."""
    ap.record_llm_call({"type": "chat_completion", "model": "m", "error": "rate limited"})
    llm = _tasks(capture["records"], "llm_call")[0]
    assert llm["status"] == "ERROR"
    assert llm["generated"]["error"] == "rate limited"
