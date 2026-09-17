"""Tests for the in-process SDK wrappers.

The three SDKs are duck-typed, so these drive each wrapper with objects shaped
like the real payloads rather than requiring the SDKs to be installed. Where an
SDK *is* installed, a further test drives the real thing.
"""

from __future__ import annotations

import pytest

from flowcept.agents.harness import SessionTracer
from flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin import ClaudeAgentTracer
from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler
from flowcept.agents.openai_agents.openai_agents_plugin import FlowceptTraceProcessor
from flowcept.agents.harness.vocab import AGENT_TOOL, AI_MODEL_INVOCATION, HARNESS_EVENT, SUBAGENT_SESSION


def tasks(records, subtype=None):
    return [r for r in records if r.get("type") == "task" and (subtype is None or r.get("subtype") == subtype)]


def workflows(records, subtype=None):
    return [r for r in records if r.get("type") == "workflow" and (subtype is None or r.get("subtype") == subtype)]


# -- SessionTracer ------------------------------------------------------------


def test_tracer_records_a_whole_run(config, buffer_records):
    with SessionTracer("my_agent", "run-1", config=config, model="claude-opus-5") as tracer:
        tracer.prompt("summarize the repo")
        call = tracer.tool_start("read_file", {"path": "README.md"})
        tracer.tool_end(call, tool_response={"bytes": 4096})
        tracer.turn_end("done", usage={"input_tokens": 900, "output_tokens": 30})

    records = buffer_records()
    turn = tasks(records, AI_MODEL_INVOCATION)[0]
    tool = tasks(records, AGENT_TOOL)[0]
    assert turn["used"]["prompt"] == "summarize the repo"
    assert turn["custom_metadata"]["llm_usage"]["input_tokens"] == 900
    assert tool["activity_id"] == "read_file"
    assert tool["generated"]["bytes"] == 4096
    # The tool hangs off the turn, which is the edge the whole thing is for.
    assert tool["parent_task_id"] == turn["task_id"]

    session = workflows(records)[-1]
    assert session["status"] == "FINISHED"
    assert session["generated"] == {"turns": 1, "tool_calls": 1}


def test_tool_context_manager_records_a_raised_exception(config, buffer_records):
    tracer = SessionTracer("my_agent", "run-2", config=config)
    with pytest.raises(ValueError):
        with tracer.tool("run_tests", {"suite": "unit"}) as call:
            call.result({"ignored": True})
            raise ValueError("boom")

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "ValueError: boom"


def test_tracer_end_is_idempotent(config, buffer_records):
    tracer = SessionTracer("my_agent", "run-3", config=config)
    tracer.prompt("hi")
    tracer.end()
    tracer.end()
    assert len([w for w in workflows(buffer_records()) if w.get("status") == "FINISHED"]) == 1


def test_an_interrupted_run_still_closes_its_turn(config, buffer_records):
    """A crash mid-turn must leave attributable provenance, not nothing."""
    with pytest.raises(RuntimeError):
        with SessionTracer("my_agent", "run-4", config=config) as tracer:
            tracer.prompt("long job")
            raise RuntimeError("killed")

    turn = tasks(buffer_records(), AI_MODEL_INVOCATION)[0]
    assert turn["custom_metadata"]["close_reason"] == "session_ended"
    assert workflows(buffer_records())[-1]["custom_metadata"]["end_reason"] == "error"


# -- Claude Agent SDK ---------------------------------------------------------


class Block:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class AssistantMessage:
    def __init__(self, content, model="claude-opus-5"):
        self.content = content
        self.model = model


class UserMessage:
    def __init__(self, content):
        self.content = content


class ResultMessage:
    def __init__(self, result=None, usage=None, is_error=False, session_id=None):
        self.result = result
        self.usage = usage
        self.is_error = is_error
        self.session_id = session_id
        self.num_turns = 1
        self.total_cost_usd = 0.01


class SystemMessage:
    def __init__(self, subtype, data=None):
        self.subtype = subtype
        self.data = data or {}


def test_claude_agent_stream_becomes_provenance(config, buffer_records):
    with ClaudeAgentTracer(config=config, prompt="fix the failing test") as tracer:
        tracer.handle(
            AssistantMessage(
                [
                    Block(text="Let me look."),
                    Block(id="tu_1", name="Read", input={"file_path": "test_x.py"}),
                ]
            )
        )
        tracer.handle(UserMessage([Block(tool_use_id="tu_1", content="def test_x(): ...", is_error=False)]))
        tracer.handle(ResultMessage(result="fixed", usage={"input_tokens": 1200, "output_tokens": 80}))

    records = buffer_records()
    turn = tasks(records, AI_MODEL_INVOCATION)[0]
    assert turn["used"]["prompt"] == "fix the failing test"
    assert turn["generated"]["response"] == "fixed"
    # Cost travels with usage; both are on the turn, which is where a query for
    # "what did this session cost" will look.
    assert turn["custom_metadata"]["llm_usage"]["total_cost_usd"] == 0.01
    assert turn["custom_metadata"]["llm_usage"]["input_tokens"] == 1200

    tool = tasks(records, AGENT_TOOL)[0]
    assert tool["activity_id"] == "Read"
    assert tool["used"]["file_path"] == "test_x.py"
    assert tool["status"] == "FINISHED"


def test_claude_agent_adopts_the_sdk_session_id(config, buffer_records):
    """The init message's id is taken, so a resumed run reuses the workflow."""
    tracer = ClaudeAgentTracer(config=config)
    tracer.handle(SystemMessage("init", {"session_id": "sdk-abc", "model": "claude-opus-5"}))
    tracer.handle(AssistantMessage([Block(text="hi")]))
    tracer.close()

    assert tracer.tracer.session_id == "sdk-abc"

    from flowcept.agents.harness import ids

    expected = ids.workflow_id_for("claude_agent_sdk", "sdk-abc")
    assert {r["workflow_id"] for r in buffer_records()} == {expected}


def test_claude_agent_keeps_an_explicit_session_id(config):
    tracer = ClaudeAgentTracer("mine", config=config)
    tracer.handle(SystemMessage("init", {"session_id": "sdk-abc"}))
    assert tracer.tracer.session_id == "mine"


def test_claude_agent_task_tool_opens_a_subagent_workflow(config, buffer_records):
    with ClaudeAgentTracer(config=config, prompt="explore") as tracer:
        tracer.handle(
            AssistantMessage(
                [Block(id="tu_task", name="Task", input={"subagent_type": "Explore", "prompt": "find the tests"})]
            )
        )
        tracer.handle(UserMessage([Block(tool_use_id="tu_task", content="found 3", is_error=False)]))
        tracer.handle(ResultMessage(result="ok"))

    subagent = workflows(buffer_records(), SUBAGENT_SESSION)
    assert len(subagent) == 1  # opened and closed, the open record superseded
    assert subagent[0]["used"] == {"agent_type": "Explore", "prompt": "find the tests"}
    assert subagent[0]["generated"]["response"] == "found 3"
    assert subagent[0]["status"] == "FINISHED"


def test_claude_agent_tool_opens_a_subagent_workflow(config, buffer_records):
    """The subagent tool is named `Agent` on newer CLIs and `Task` on older ones."""
    with ClaudeAgentTracer(config=config, prompt="explore") as tracer:
        tracer.handle(
            AssistantMessage(
                [Block(id="tu_agent", name="Agent", input={"subagent_type": "Explore", "prompt": "find the tests"})]
            )
        )
        tracer.handle(UserMessage([Block(tool_use_id="tu_agent", content="found 3", is_error=False)]))
        tracer.handle(ResultMessage(result="ok"))

    subagent = workflows(buffer_records(), SUBAGENT_SESSION)
    assert len(subagent) == 1
    assert subagent[0]["used"] == {"agent_type": "Explore", "prompt": "find the tests"}


def test_claude_agent_ignores_progress_system_messages(config, buffer_records):
    """`thinking_tokens` is a progress ticker, not provenance."""
    with ClaudeAgentTracer(config=config, prompt="p") as tracer:
        for _ in range(5):
            tracer.handle(SystemMessage("thinking_tokens", {"count": 120}))
        tracer.handle(ResultMessage(result="ok"))

    assert tasks(buffer_records(), HARNESS_EVENT) == []


def test_claude_agent_records_a_compaction(config, buffer_records):
    with ClaudeAgentTracer(config=config, prompt="p") as tracer:
        tracer.handle(SystemMessage("compact_boundary", {}))
        tracer.handle(ResultMessage(result="ok"))

    events = tasks(buffer_records(), HARNESS_EVENT)
    assert len(events) == 1
    assert events[0]["activity_id"] == "compact"


def test_claude_agent_failed_tool_is_an_error(config, buffer_records):
    with ClaudeAgentTracer(config=config, prompt="p") as tracer:
        tracer.handle(AssistantMessage([Block(id="tu_1", name="Bash", input={"command": "false"})]))
        tracer.handle(UserMessage([Block(tool_use_id="tu_1", content="exit status 1", is_error=True)]))

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "exit status 1"


def test_claude_agent_closes_a_tool_that_never_returned(config, buffer_records):
    tracer = ClaudeAgentTracer(config=config, prompt="p")
    tracer.handle(AssistantMessage([Block(id="tu_1", name="Bash", input={"command": "sleep 999"})]))
    tracer.close(error="interrupted")

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "never returned a result"


def test_claude_agent_records_nothing_for_an_empty_run(config, buffer_records):
    ClaudeAgentTracer(config=config).close()
    assert buffer_records() == []


def test_claude_agent_compaction_is_a_lifecycle_event(config, buffer_records):
    tracer = ClaudeAgentTracer(config=config, prompt="p")
    tracer.handle(AssistantMessage([Block(text="working")]))
    tracer.handle(SystemMessage("compact_boundary"))
    tracer.close()

    assert [t["activity_id"] for t in tasks(buffer_records(), "harness_event")] == ["compact"]


# -- OpenAI Agents SDK --------------------------------------------------------


class Trace:
    def __init__(self, trace_id="tr_1", group_id=None, name="run"):
        self.trace_id = trace_id
        self.group_id = group_id
        self.name = name


class Span:
    def __init__(self, span_id, data, *, trace_id="tr_1", parent_id=None, error=None):
        self.span_id = span_id
        self.trace_id = trace_id
        self.parent_id = parent_id
        self.span_data = data
        self.error = error
        self.started_at = "2026-08-19T10:00:00+00:00"
        self.ended_at = "2026-08-19T10:00:02+00:00"


class SpanData:
    def __init__(self, type, **fields):
        self.type = type
        self.__dict__.update(fields)


def test_openai_agents_trace_becomes_a_session(config, buffer_records):
    processor = FlowceptTraceProcessor(config)
    trace = Trace(group_id="thread-9")
    processor.on_trace_start(trace)

    generation = Span("sp_1", SpanData("generation", model="gpt-5", input="hi", output="hello",
                                       usage={"input_tokens": 10, "output_tokens": 3}))
    processor.on_span_start(generation)
    processor.on_span_end(generation)

    function = Span("sp_2", SpanData("function", name="get_weather", input='{"city": "Paris"}', output="18C"))
    processor.on_span_start(function)
    processor.on_span_end(function)

    processor.on_trace_end(trace)

    records = buffer_records()
    call = next(t for t in tasks(records, AI_MODEL_INVOCATION) if t["activity_id"] == "llm_interaction")
    assert call["custom_metadata"]["model"] == "gpt-5"
    assert call["custom_metadata"]["llm_usage"]["output_tokens"] == 3
    # The span reported its own duration; it must survive.
    assert call["ended_at"] - call["started_at"] == pytest.approx(2.0, abs=0.01)

    tool = tasks(records, AGENT_TOOL)[0]
    assert tool["activity_id"] == "get_weather"
    assert tool["generated"]["value"] == "18C"

    session = workflows(records)[-1]
    assert session["status"] == "FINISHED"


def test_openai_agents_nested_agent_becomes_a_subagent(config, buffer_records):
    processor = FlowceptTraceProcessor(config)
    trace = Trace()
    processor.on_trace_start(trace)

    root = Span("sp_root", SpanData("agent", name="Triage", model="gpt-5"))
    processor.on_span_start(root)
    nested = Span("sp_sub", SpanData("agent", name="Researcher", output="found it"), parent_id="sp_root")
    processor.on_span_start(nested)
    tool = Span("sp_tool", SpanData("function", name="search", output="hits"), parent_id="sp_sub")
    processor.on_span_start(tool)
    processor.on_span_end(tool)
    processor.on_span_end(nested)
    processor.on_span_end(root)
    processor.on_trace_end(trace)

    records = buffer_records()
    subagents = workflows(records, SUBAGENT_SESSION)
    assert [w["name"] for w in subagents] == ["subagent:Researcher"]
    # A root agent is the session, so it must not also become a subagent.
    assert not any("Triage" in w["name"] for w in subagents)
    # The nested agent's tool belongs to the nested agent's workflow.
    assert tasks(records, AGENT_TOOL)[0]["workflow_id"] == subagents[0]["workflow_id"]


def test_openai_agents_span_error_marks_the_tool_failed(config, buffer_records):
    processor = FlowceptTraceProcessor(config)
    trace = Trace()
    processor.on_trace_start(trace)
    span = Span("sp_1", SpanData("function", name="deploy"), error={"message": "denied", "data": "no creds"})
    processor.on_span_start(span)
    processor.on_span_end(span)
    processor.on_trace_end(trace)

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "denied: no creds"


def test_openai_agents_tripped_guardrail_is_an_error(config, buffer_records):
    processor = FlowceptTraceProcessor(config)
    trace = Trace()
    processor.on_trace_start(trace)
    span = Span("sp_1", SpanData("guardrail", name="no_pii", triggered=True))
    processor.on_span_start(span)
    processor.on_span_end(span)
    processor.on_trace_end(trace)

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["activity_id"] == "no_pii"
    assert tool["stderr"] == "guardrail triggered"


def test_openai_agents_ignores_spans_from_an_unknown_trace(config, buffer_records):
    """Spans can outlive their trace; they must not create a phantom session."""
    processor = FlowceptTraceProcessor(config)
    processor.on_span_end(Span("sp_1", SpanData("function", name="x")))
    assert buffer_records() == []


def test_openai_agents_shutdown_closes_open_traces(config, buffer_records):
    processor = FlowceptTraceProcessor(config)
    processor.on_trace_start(Trace())
    processor.shutdown()
    assert workflows(buffer_records())[-1]["custom_metadata"]["end_reason"] == "shutdown"


# -- LangChain / LangGraph ----------------------------------------------------


class Generation:
    def __init__(self, text):
        self.text = text
        self.message = None


class LLMResult:
    def __init__(self, text, llm_output=None):
        self.generations = [[Generation(text)]]
        self.llm_output = llm_output


def test_langchain_chain_run_becomes_a_turn(config, buffer_records):
    handler = FlowceptCallbackHandler("thread-1", config=config)
    handler.on_chain_start({"name": "AgentExecutor"}, {"input": "what is 2+2"}, run_id="r0")
    handler.on_llm_start(
        {"name": "ChatOpenAI"}, ["what is 2+2"], run_id="r1", parent_run_id="r0",
        invocation_params={"model": "gpt-5"},
    )
    handler.on_llm_end(LLMResult("4", {"token_usage": {"prompt_tokens": 12, "completion_tokens": 1}}), run_id="r1")
    handler.on_chain_end({"output": "4"}, run_id="r0")
    handler.close()

    records = buffer_records()
    turn = next(t for t in tasks(records, AI_MODEL_INVOCATION) if t["activity_id"] == "agent_turn")
    assert turn["used"]["prompt"] == "what is 2+2"
    assert turn["generated"]["response"] == "4"

    call = next(t for t in tasks(records, AI_MODEL_INVOCATION) if t["activity_id"] == "llm_interaction")
    assert call["custom_metadata"]["model"] == "gpt-5"
    assert call["custom_metadata"]["llm_usage"]["prompt_tokens"] == 12
    # The call nests under the turn, not beside it.
    assert call["parent_task_id"] == turn["task_id"]


def test_langchain_tool_run_becomes_a_tool_task(config, buffer_records):
    handler = FlowceptCallbackHandler("thread-2", config=config)
    handler.on_chain_start(None, {"input": "weather?"}, run_id="r0")
    handler.on_tool_start({"name": "get_weather"}, '{"city": "Paris"}', run_id="r1",
                          parent_run_id="r0", inputs={"city": "Paris"})
    handler.on_tool_end("18C", run_id="r1")
    handler.on_chain_end({"output": "18C"}, run_id="r0")
    handler.close()

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["activity_id"] == "get_weather"
    assert tool["used"] == {"city": "Paris"}
    assert tool["generated"]["value"] == "18C"


def test_langchain_nested_chains_are_not_recorded(config, buffer_records):
    """A LangGraph run emits a chain per node; only the outer one is a turn."""
    handler = FlowceptCallbackHandler("thread-3", config=config)
    handler.on_chain_start(None, {"messages": ["go"]}, run_id="r0")
    for node in ("agent", "tools", "agent"):
        handler.on_chain_start({"name": node}, {}, run_id=f"n_{node}", parent_run_id="r0")
        handler.on_chain_end({}, run_id=f"n_{node}")
    handler.on_chain_end({"messages": ["done"]}, run_id="r0")
    handler.close()

    assert len(tasks(buffer_records(), AI_MODEL_INVOCATION)) == 1


def test_langchain_tool_error_is_recorded(config, buffer_records):
    handler = FlowceptCallbackHandler("thread-4", config=config)
    handler.on_tool_start({"name": "deploy"}, "", run_id="r1")
    handler.on_tool_error(RuntimeError("denied"), run_id="r1")
    handler.close()

    tool = tasks(buffer_records(), AGENT_TOOL)[0]
    assert tool["status"] == "ERROR"
    assert tool["stderr"] == "RuntimeError: denied"


def test_langchain_bare_model_call_is_its_own_turn(config, buffer_records):
    """No chain around it: the model call is the whole turn."""
    handler = FlowceptCallbackHandler("thread-5", config=config)
    handler.on_llm_start({"id": ["langchain", "ChatAnthropic"]}, ["hello"], run_id="r1")
    handler.on_llm_end(LLMResult("hi there"), run_id="r1")
    handler.close()

    turn = next(t for t in tasks(buffer_records(), AI_MODEL_INVOCATION) if t["activity_id"] == "agent_turn")
    assert turn["used"]["prompt"] == "hello"
    assert turn["generated"]["response"] == "hi there"
    assert turn["status"] == "FINISHED"


def test_langchain_chain_error_marks_the_turn_failed(config, buffer_records):
    handler = FlowceptCallbackHandler("thread-6", config=config)
    handler.on_chain_start(None, {"input": "x"}, run_id="r0")
    handler.on_chain_error(ValueError("bad graph"), run_id="r0")
    handler.close()

    turn = tasks(buffer_records(), AI_MODEL_INVOCATION)[0]
    assert turn["status"] == "ERROR"
    assert turn["stderr"] == "ValueError: bad graph"


def test_langchain_chat_model_start_flattens_messages(config, buffer_records):
    class Message:
        def __init__(self, type, content):
            self.type = type
            self.content = content

    handler = FlowceptCallbackHandler("thread-7", config=config)
    handler.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[Message("system", "be brief"), Message("human", "hi")]],
        run_id="r1",
        invocation_params={"model": "gpt-5"},
    )
    handler.on_llm_end(LLMResult("hello"), run_id="r1")
    handler.close()

    call = next(t for t in tasks(buffer_records(), AI_MODEL_INVOCATION) if t["activity_id"] == "llm_interaction")
    assert call["used"]["prompt"] == "system: be brief\nhuman: hi"


def test_langchain_handler_exposes_the_manager_contract(config):
    """langchain's callback manager reads these off the handler by name."""
    handler = FlowceptCallbackHandler(config=config)
    for attribute in ("ignore_llm", "ignore_chain", "ignore_agent", "ignore_retriever",
                      "ignore_chat_model", "ignore_retry", "ignore_custom_event",
                      "raise_error", "run_inline"):
        assert isinstance(getattr(handler, attribute), bool)
