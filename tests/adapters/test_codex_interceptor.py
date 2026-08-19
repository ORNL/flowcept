"""Replay tests for the Codex provenance adapter."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from flowcept.commons.vocabulary import PROV_AGENT, PROV_AGENT_LOOP
from flowcept.flowceptor.adapters.code_assistants.codex.codex_interceptor import (
    CodexInterceptor,
)


ALLOWED_ENTITY_TYPES = {
    "entity",
    "objective",
    "plan",
    "checkpoint",
    "message",
    "evaluation_criteria",
    "evaluation_result",
    "memory",
    "lesson_learned",
    "observation",
    "thought",
    "decision",
    "mandate",
    "user_prompt",
    "agent_response",
    "belief",
    "ai_model",
    "tool",
    "domain_data",
    "scheduling_data",
    "telemetry_data",
}


def _event(timestamp: str, event_type: str, payload: dict) -> dict:
    return {"timestamp": timestamp, "type": event_type, "payload": payload}


def _message_payload(role: str, text: str, *, turn_id: str, phase: str | None = None) -> dict:
    payload = {
        "type": "message",
        "role": role,
        "content": [{"type": "output_text" if role == "assistant" else "input_text", "text": text}],
        "internal_chat_message_metadata_passthrough": {"turn_id": turn_id},
    }
    if phase:
        payload["phase"] = phase
    return payload


def _write_jsonl(path: Path, events: list[dict]):
    path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")


def _new_interceptor(*, declared_provenance_enabled: bool) -> tuple[CodexInterceptor, list[dict]]:
    interceptor = CodexInterceptor.__new__(CodexInterceptor)
    records: list[dict] = []
    interceptor.plugin_key = "codex"
    interceptor.settings = SimpleNamespace(
        declared_provenance_enabled=declared_provenance_enabled,
        include_developer_messages=True,
        include_reasoning=True,
        watch_interval_sec=0,
        file_path="",
        recursive=False,
    )
    interceptor._observer = None
    interceptor._processed_lines = {}
    interceptor._session_id = None
    interceptor._codex_agent_id = None
    interceptor._human_agent_id = None
    interceptor._model_provider = None
    interceptor._current_turn_id = None
    interceptor._active_execution_plan_workflow_id = None
    interceptor._pending_execution_plan_workflow_id = None
    interceptor._pending_execution_plan_turn_id = None
    interceptor._execution_plan_criteria = {}
    interceptor._execution_plan_steps = {}
    interceptor._execution_plan_finished_steps = {}
    interceptor._tagged_task_counts = {}
    interceptor._active_tagged_tasks = {}
    interceptor._processed_declared_events = set()
    interceptor._emitted_task_bounds = {}
    interceptor._turns = {}
    interceptor._emitted_records_count = 0
    interceptor._mq_dao = SimpleNamespace(buffer=SimpleNamespace(current_buffer=records))
    interceptor.intercept = lambda record: records.append(record)
    interceptor.send_workflow_message = lambda obj: records.append(obj.to_dict())
    interceptor.send_agent_message = lambda obj: records.append(obj.to_dict())
    return interceptor, records


def _replay(path: Path, *, declared_provenance_enabled: bool = True) -> list[dict]:
    interceptor, records = _new_interceptor(declared_provenance_enabled=declared_provenance_enabled)
    interceptor._process_log(path)
    interceptor._flush_open_records()
    return records


def _tasks(records: list[dict]) -> list[dict]:
    return [record for record in records if record.get("type") == "task"]


def _workflows(records: list[dict]) -> list[dict]:
    return [record for record in records if record.get("type") == "workflow"]


def _assert_common_invariants(records: list[dict]):
    tasks = _tasks(records)
    by_id = {task["task_id"]: task for task in tasks}
    for record in [*_workflows(records), *tasks]:
        for side in ("used", "generated"):
            payload = record.get(side) or {}
            allowed_keys = {"entities"}
            if record.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value and side == "used":
                allowed_keys.add("prompt")
            if record.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value and side == "generated":
                allowed_keys.add("response")
            assert set(payload).issubset(allowed_keys)
            for entity in payload.get("entities") or []:
                assert entity.get("type") in ALLOWED_ENTITY_TYPES
                assert "entity_role" not in entity
    for task in tasks:
        if task.get("started_at"):
            assert task.get("utc_timestamp") == task.get("started_at")
        if task.get("subtype") in {
            PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value,
            PROV_AGENT_LOOP.LOOP_ITERATION.value,
        }:
            assert not task.get("generated")
        parent = by_id.get(task.get("parent_task_id"))
        if not parent:
            continue
        assert task.get("workflow_id") == parent.get("workflow_id")
        if task.get("started_at") and parent.get("started_at"):
            assert task["started_at"] >= parent["started_at"]
        if task.get("ended_at") and parent.get("ended_at"):
            assert task["ended_at"] <= parent["ended_at"]
    execution_plan_workflows = {
        workflow["workflow_id"]
        for workflow in _workflows(records)
        if workflow.get("subtype") == PROV_AGENT_LOOP.EXECUTION_PLAN.value
    }
    for task in tasks:
        if task.get("workflow_id") not in execution_plan_workflows:
            continue
        if task.get("subtype") in {
            PROV_AGENT.AI_MODEL_INVOCATION.value,
            PROV_AGENT.TOOL_INVOCATION.value,
            PROV_AGENT_LOOP.EVALUATION.value,
        }:
            assert task.get("parent_task_id")


def test_dpl_execution_plan_does_not_parent_plan_generation_turn(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    plan = """**Execution Plan**

**Summary**
- Build a small package.

**Steps**
- `Inspect tutorial`
- `Create package`

**Evaluation criteria**
- YAML files parse.
"""
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            _message_payload("assistant", f"<proposed_plan>\n{plan}\n</proposed_plan>", turn_id="turn-plan"),
        ),
        _event(
            "2026-08-03T10:00:04Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 1, "output_tokens": 1}}},
        ),
        _event(
            "2026-08-03T10:00:05Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-plan", "last_agent_message": "plan ready"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    workflows = _workflows(records)
    tasks = _tasks(records)
    execution_plan = next(w for w in workflows if w.get("subtype") == PROV_AGENT_LOOP.EXECUTION_PLAN.value)
    plan_invocation = next(t for t in tasks if t.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value)

    assert plan_invocation["workflow_id"] == "s1"
    assert execution_plan["parent_workflow_id"] == "s1"
    assert execution_plan.get("status") == "RUNNING"
    assert execution_plan.get("ended_at") is None
    assert [
        task
        for task in tasks
        if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value
        and task.get("workflow_id") == "s1"
    ] == []


def test_dpl_tagged_step_loop_parents_observed_invocations_and_tools(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    start_tags = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Inspect tutorial"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Inspect tutorial loop"}</flowcept_event>'
    )
    finish_tags = (
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Inspect tutorial loop","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Inspect tutorial","status":"finished"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Inspect tutorial"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event(
            "2026-08-03T10:00:04Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 1, "output_tokens": 1}}},
        ),
        _event(
            "2026-08-03T10:00:05Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-plan", "last_agent_message": "plan ready"},
        ),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-step"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event("2026-08-03T10:01:02Z", "response_item", _message_payload("assistant", start_tags, turn_id="turn-step")),
        _event(
            "2026-08-03T10:01:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "pwd"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-step"},
            },
        ),
        _event(
            "2026-08-03T10:01:04Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-step"},
            },
        ),
        _event("2026-08-03T10:01:05Z", "response_item", _message_payload("assistant", finish_tags, turn_id="turn-step")),
        _event(
            "2026-08-03T10:01:06Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 1, "output_tokens": 1}}},
        ),
        _event(
            "2026-08-03T10:01:07Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-step", "last_agent_message": "done"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    counts = Counter(task.get("subtype") for task in tasks)
    assert counts[PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value] == 1
    assert counts[PROV_AGENT_LOOP.LOOP_ITERATION.value] == 1

    loop = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value)
    step = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
    assert step["started_at"] < loop["started_at"]
    children = [task for task in tasks if task.get("parent_task_id") == loop["task_id"]]
    assert all(loop["started_at"] <= task["started_at"] for task in children)
    assert {task.get("subtype") for task in children} >= {
        PROV_AGENT.AI_MODEL_INVOCATION.value,
        PROV_AGENT.TOOL_INVOCATION.value,
    }
    tool = next(task for task in children if task.get("subtype") == PROV_AGENT.TOOL_INVOCATION.value)
    assert (tool.get("used") or {})["entities"][1]["type"] == "domain_data"
    assert (tool.get("generated") or {})["entities"][0]["type"] == "domain_data"


def test_dpl_does_not_create_second_execution_plan_workflow(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    plan_a = "<proposed_plan>\n**Plan A**\n\n**Steps**\n- `Create file`\n</proposed_plan>"
    plan_b = "<proposed_plan>\n**Plan B**\n\n**Steps**\n- `Run tests`\n</proposed_plan>"
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event("2026-08-03T10:00:03Z", "response_item", _message_payload("assistant", plan_a, turn_id="turn-plan")),
        _event("2026-08-03T10:00:04Z", "event_msg", {"type": "task_complete", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "continue"}),
        _event("2026-08-03T10:01:02Z", "response_item", _message_payload("assistant", plan_b, turn_id="turn-work")),
        _event("2026-08-03T10:01:03Z", "event_msg", {"type": "task_complete", "turn_id": "turn-work"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    execution_plans = [
        workflow
        for workflow in _workflows(records)
        if workflow.get("subtype") == PROV_AGENT_LOOP.EXECUTION_PLAN.value
    ]

    assert len(execution_plans) == 1


def test_loop_start_reparents_existing_commentary_invocation_before_tool(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    tags = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Implement"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Implement loop"}</flowcept_event>'
    )
    finish = (
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Implement loop","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Implement","status":"finished"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            _message_payload("assistant", "Vou implementar agora.", turn_id="turn-1", phase="commentary"),
        ),
        _event("2026-08-03T10:00:04Z", "response_item", _message_payload("assistant", tags, turn_id="turn-1")),
        _event(
            "2026-08-03T10:00:05Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "pwd"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-1"},
            },
        ),
        _event(
            "2026-08-03T10:00:06Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-1"},
            },
        ),
        _event("2026-08-03T10:00:07Z", "response_item", _message_payload("assistant", finish, turn_id="turn-1")),
        _event("2026-08-03T10:00:08Z", "event_msg", {"type": "task_complete", "turn_id": "turn-1"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    loop = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value)
    children = [task for task in tasks if task.get("parent_task_id") == loop["task_id"]]

    assert any(task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value for task in children)
    assert any(task.get("subtype") == PROV_AGENT.TOOL_INVOCATION.value for task in children)


def test_dpl_without_step_tags_creates_execution_plan_loop_from_turn(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Create package"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event(
            "2026-08-03T10:00:04Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-plan", "last_agent_message": "plan ready"},
        ),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event(
            "2026-08-03T10:01:02Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "pwd"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:03Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:04Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-work", "last_agent_message": "done"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    execution_plan_id = next(
        workflow["workflow_id"]
        for workflow in _workflows(records)
        if workflow.get("subtype") == PROV_AGENT_LOOP.EXECUTION_PLAN.value
    )
    execution_plan_loops = [
        task
        for task in _tasks(records)
        if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value
        and task.get("workflow_id") == execution_plan_id
    ]
    assert len(execution_plan_loops) == 1
    loop = execution_plan_loops[0]
    assert loop.get("parent_task_id") is None
    children = [
        task
        for task in _tasks(records)
        if task.get("parent_task_id") == loop["task_id"]
    ]
    assert {task.get("subtype") for task in children} >= {
        PROV_AGENT.AI_MODEL_INVOCATION.value,
        PROV_AGENT.TOOL_INVOCATION.value,
    }


def test_tool_data_entity_type_classifies_scheduling_and_telemetry():
    interceptor, _ = _new_interceptor(declared_provenance_enabled=True)
    tool = SimpleNamespace(tool_name="exec_command", arguments={"cmd": "sacct -j 123 --format JobID,Elapsed"})
    assert interceptor._tool_data_entity_type(tool, tool.arguments) == "scheduling_data"

    tool = SimpleNamespace(tool_name="exec_command", arguments={"cmd": "nvidia-smi --query-gpu=utilization.gpu"})
    assert interceptor._tool_data_entity_type(tool, tool.arguments) == "telemetry_data"


def test_token_count_then_task_complete_populates_ai_model_response(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "say done"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            _message_payload("assistant", "Vou responder no final.", turn_id="turn-1", phase="commentary"),
        ),
        _event(
            "2026-08-03T10:00:04Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 3, "output_tokens": 5}}},
        ),
        _event(
            "2026-08-03T10:00:05Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": "done"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    invocation = next(task for task in _tasks(records) if task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value)
    generated = invocation.get("generated") or {}
    entities = generated.get("entities") or []

    assert generated.get("response") == "done"
    assert any(entity.get("type") == "agent_response" and entity.get("content") == "done" for entity in entities)
    assert invocation.get("custom_metadata", {}).get("llm_usage", {}).get("input_tokens") == 3


def test_dpl_semantic_entities_are_captured_from_declared_events(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    dpl = "\n".join(
        [
            '<flowcept_event>{"layer":"DPL","class":"Observation","summary":"The validation command failed."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"Belief","summary":"The config path is wrong."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"Decision","decision":"retry","summary":"Patch the config path."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"Memory","summary":"This repo stores configs under conf/."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"lesson_learned","summary":"Validate config paths before launching training."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"EvaluationCriteria","summary":"Validation loss stays below threshold."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"evaluation_result","summary":"Validation failed before launch."}</flowcept_event>',
        ]
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "validate"}),
        _event("2026-08-03T10:00:03Z", "response_item", _message_payload("assistant", dpl, turn_id="turn-1")),
        _event(
            "2026-08-03T10:00:04Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": "done"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    invocation = next(task for task in _tasks(records) if task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value)
    entity_types = {
        entity.get("type")
        for entity in (invocation.get("generated") or {}).get("entities") or []
    }

    assert {
        "observation",
        "belief",
        "decision",
        "memory",
        "lesson_learned",
        "evaluation_criteria",
        "evaluation_result",
    } <= entity_types


def test_opl_ignores_declared_event_only_messages(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    dpl_only = "\n".join(
        [
            '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started","label":"Create file"}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started","label":"Create file loop"}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"Observation","summary":"The file was created."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"Belief","summary":"The file exists."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"Memory","summary":"Use uv run for pytest."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"LessonLearned","summary":"Validate after writing."}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished","label":"Create file loop","status":"finished"}</flowcept_event>',
            '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished","label":"Create file","status":"finished"}</flowcept_event>',
        ]
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Create file"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event("2026-08-03T10:00:04Z", "event_msg", {"type": "task_complete", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event("2026-08-03T10:01:02Z", "event_msg", {"type": "agent_message", "message": dpl_only}),
        _event(
            "2026-08-03T10:01:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "touch file.txt"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:04Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event("2026-08-03T10:01:05Z", "event_msg", {"type": "task_complete", "turn_id": "turn-work"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log, declared_provenance_enabled=False)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    entity_types = {
        entity.get("type")
        for task in tasks
        for side in ("used", "generated")
        for entity in (task.get(side) or {}).get("entities") or []
    }

    assert PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value not in {task.get("subtype") for task in tasks}
    assert PROV_AGENT_LOOP.EVALUATION.value not in {task.get("subtype") for task in tasks}
    assert not {"observation", "belief", "memory", "lesson_learned"} & entity_types


def test_dpl_only_bridge_message_does_not_create_zero_duration_model_invocation(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    plan_tags = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Create file"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Create file loop"}</flowcept_event>'
    )
    bridge_tags = (
        '<flowcept_event>{"layer":"DPL","class":"Observation","summary":"The file was created."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"Decision","decision":"continue",'
        '"summary":"Proceed to tests."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Create file loop","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Create file","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Run tests"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Run tests loop"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Create file"}, {"step": "Run tests"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event(
            "2026-08-03T10:00:04Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-plan", "last_agent_message": "plan ready"},
        ),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event("2026-08-03T10:01:02Z", "response_item", _message_payload("assistant", plan_tags, turn_id="turn-work")),
        _event(
            "2026-08-03T10:01:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "touch file.txt"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:04Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:05Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 3, "output_tokens": 4}}},
        ),
        _event("2026-08-03T10:01:06Z", "event_msg", {"type": "agent_message", "message": bridge_tags}),
        _event(
            "2026-08-03T10:01:07Z",
            "event_msg",
            {"type": "task_complete", "turn_id": "turn-work", "last_agent_message": "done"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    ai_invocations = [task for task in tasks if task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value]
    assert len([task for task in ai_invocations if task["task_id"].startswith("turn-work:")]) == 1
    assert Counter(task.get("subtype") for task in tasks)[PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value] == 1
    work_invocation = next(
        task
        for task in ai_invocations
        if task["task_id"].startswith("turn-work:")
    )
    generated_types = {
        entity.get("type")
        for entity in (work_invocation.get("generated") or {}).get("entities") or []
    }
    assert {"observation", "decision"} <= generated_types


def test_tool_only_model_invocation_has_ui_response(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "run pwd"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "pwd"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-1"},
            },
        ),
        _event(
            "2026-08-03T10:00:04Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-1"},
            },
        ),
        _event(
            "2026-08-03T10:00:05Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 3, "output_tokens": 4}}},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    invocation = next(task for task in _tasks(records) if task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value)

    assert (invocation.get("generated") or {}).get("response") == "Requested tool invocation: exec_command"


def test_dpl_multiple_retry_loops_can_share_one_plan_step(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    start = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Run focused tests"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Try pytest with python"}</flowcept_event>'
    )
    retry = (
        '<flowcept_event>{"layer":"DPL","class":"Evaluation","event":"finished",'
        '"label":"Try pytest with python","status":"failed","decision":"retry",'
        '"result":"python is unavailable."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"Observation","summary":"python is unavailable."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"Decision","decision":"retry",'
        '"summary":"Retry with python3."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Try pytest with python","status":"failed"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Retry pytest with python3"}</flowcept_event>'
    )
    finish = (
        '<flowcept_event>{"layer":"DPL","class":"Evaluation","event":"finished",'
        '"label":"Retry pytest with python3","status":"passed","decision":"continue",'
        '"result":"tests passed."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"Decision","decision":"continue",'
        '"summary":"Finish the step."}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Retry pytest with python3","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Run focused tests","status":"finished"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Run focused tests"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event("2026-08-03T10:00:04Z", "event_msg", {"type": "task_complete", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event("2026-08-03T10:01:02Z", "response_item", _message_payload("assistant", start, turn_id="turn-work")),
        _event("2026-08-03T10:01:03Z", "event_msg", {"type": "agent_message", "message": retry}),
        _event("2026-08-03T10:01:04Z", "event_msg", {"type": "agent_message", "message": finish}),
        _event("2026-08-03T10:01:05Z", "event_msg", {"type": "task_complete", "turn_id": "turn-work"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    step = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
    loops = [task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value]

    assert len(loops) == 2
    assert all(loop.get("parent_task_id") == step["task_id"] for loop in loops)
    assert {loop.get("activity_id") for loop in loops} == {
        "Try pytest with python",
        "Retry pytest with python3",
    }


def test_file_write_containing_pytest_is_not_evaluation(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    start = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Create tests"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Create tests loop"}</flowcept_event>'
    )
    finish = (
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Create tests loop","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Create tests","status":"finished"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Create tests"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event("2026-08-03T10:00:04Z", "event_msg", {"type": "task_complete", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event("2026-08-03T10:01:02Z", "response_item", _message_payload("assistant", start, turn_id="turn-work")),
        _event(
            "2026-08-03T10:01:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "cat > test_fibonacci.py <<'PY'\nimport pytest\nPY"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:04Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event("2026-08-03T10:01:05Z", "event_msg", {"type": "agent_message", "message": finish}),
        _event("2026-08-03T10:01:06Z", "event_msg", {"type": "task_complete", "turn_id": "turn-work"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    loop = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value)
    children = [task for task in tasks if task.get("parent_task_id") == loop["task_id"]]

    assert any(task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value for task in children)
    assert any(task.get("subtype") == PROV_AGENT.TOOL_INVOCATION.value for task in children)
    assert not any(task.get("subtype") == PROV_AGENT_LOOP.EVALUATION.value for task in children)


def test_late_loop_start_reparents_open_invocation_and_tool(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    tags = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Late step"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Late loop"}</flowcept_event>'
    )
    finish = (
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Late loop","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Late step","status":"finished"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "run pwd"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call",
                "arguments": json.dumps({"cmd": "pwd"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-1"},
            },
        ),
        _event("2026-08-03T10:00:04Z", "response_item", _message_payload("assistant", tags, turn_id="turn-1")),
        _event(
            "2026-08-03T10:00:05Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-1"},
            },
        ),
        _event("2026-08-03T10:00:06Z", "response_item", _message_payload("assistant", finish, turn_id="turn-1")),
        _event("2026-08-03T10:00:07Z", "event_msg", {"type": "task_complete", "turn_id": "turn-1"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    loop = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value)
    invocation = next(task for task in tasks if task.get("subtype") == PROV_AGENT.AI_MODEL_INVOCATION.value)
    tool = next(task for task in tasks if task.get("subtype") == PROV_AGENT.TOOL_INVOCATION.value)

    assert invocation["parent_task_id"] == loop["task_id"]
    assert tool["parent_task_id"] == loop["task_id"]


def test_loop_start_adopts_emitted_fallback_invocation_and_tool(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    tags = (
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"started",'
        '"label":"Create package"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"started",'
        '"label":"Create package loop"}</flowcept_event>'
    )
    finish = (
        '<flowcept_event>{"layer":"DPL","class":"LoopIteration","event":"finished",'
        '"label":"Create package loop","status":"finished"}</flowcept_event>\n'
        '<flowcept_event>{"layer":"DPL","class":"PlanStepExecution","event":"finished",'
        '"label":"Create package","status":"finished"}</flowcept_event>'
    )
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Create package"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event("2026-08-03T10:00:04Z", "event_msg", {"type": "task_complete", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-work"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "implement"}),
        _event(
            "2026-08-03T10:01:02Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call-1",
                "arguments": json.dumps({"cmd": "mkdir src3"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:03Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call-1",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:04Z",
            "event_msg",
            {"type": "token_count", "info": {"last_token_usage": {"input_tokens": 1, "output_tokens": 1}}},
        ),
        _event("2026-08-03T10:01:05Z", "response_item", _message_payload("assistant", tags, turn_id="turn-work")),
        _event(
            "2026-08-03T10:01:06Z",
            "response_item",
            {
                "type": "function_call",
                "name": "exec_command",
                "call_id": "tool-call-2",
                "arguments": json.dumps({"cmd": "touch src3/__init__.py"}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event(
            "2026-08-03T10:01:07Z",
            "response_item",
            {
                "type": "function_call_output",
                "call_id": "tool-call-2",
                "output": "ok",
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-work"},
            },
        ),
        _event("2026-08-03T10:01:08Z", "response_item", _message_payload("assistant", finish, turn_id="turn-work")),
        _event("2026-08-03T10:01:09Z", "event_msg", {"type": "task_complete", "turn_id": "turn-work"}),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    tasks = _tasks(records)
    by_id = {task["task_id"]: task for task in tasks}
    step = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
    loop = next(task for task in tasks if task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value)
    children = [task for task in tasks if task.get("parent_task_id") == loop["task_id"]]

    assert loop["parent_task_id"] == step["task_id"]
    assert step["started_at"] < loop["started_at"]
    assert {task.get("subtype") for task in children} >= {
        PROV_AGENT.AI_MODEL_INVOCATION.value,
        PROV_AGENT.TOOL_INVOCATION.value,
    }
    assert all(task.get("parent_task_id") in by_id for task in tasks if task.get("parent_task_id"))


def test_aborted_turn_without_invocation_does_not_emit_empty_fallback_loop(tmp_path: Path):
    log = tmp_path / "codex.jsonl"
    events = [
        _event(
            "2026-08-03T10:00:00Z",
            "session_meta",
            {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
        ),
        _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "make a plan"}),
        _event(
            "2026-08-03T10:00:03Z",
            "response_item",
            {
                "type": "function_call",
                "name": "update_plan",
                "call_id": "plan-call",
                "arguments": json.dumps({"plan": [{"step": "Create package"}]}),
                "internal_chat_message_metadata_passthrough": {"turn_id": "turn-plan"},
            },
        ),
        _event("2026-08-03T10:00:04Z", "event_msg", {"type": "task_complete", "turn_id": "turn-plan"}),
        _event("2026-08-03T10:01:00Z", "event_msg", {"type": "task_started", "turn_id": "turn-abort"}),
        _event("2026-08-03T10:01:01Z", "event_msg", {"type": "user_message", "message": "stop"}),
        _event(
            "2026-08-03T10:01:02Z",
            "event_msg",
            {"type": "turn_aborted", "turn_id": "turn-abort", "reason": "interrupted"},
        ),
    ]
    _write_jsonl(log, events)

    records = _replay(log)
    _assert_common_invariants(records)
    assert not any(
        task.get("task_id") == "turn-abort"
        and task.get("subtype") == PROV_AGENT_LOOP.LOOP_ITERATION.value
        for task in _tasks(records)
    )


def test_codex_records_include_current_campaign_id(tmp_path: Path):
    from flowcept.flowcept_api.flowcept_controller import Flowcept

    original_campaign_id = Flowcept.campaign_id
    Flowcept.campaign_id = "campaign-test"
    try:
        log = tmp_path / "codex.jsonl"
        events = [
            _event(
                "2026-08-03T10:00:00Z",
                "session_meta",
                {"session_id": "s1", "model_provider": "openai", "base_instructions": {"text": "base"}},
            ),
            _event("2026-08-03T10:00:01Z", "event_msg", {"type": "task_started", "turn_id": "turn-1"}),
            _event("2026-08-03T10:00:02Z", "event_msg", {"type": "user_message", "message": "hello"}),
            _event(
                "2026-08-03T10:00:03Z",
                "event_msg",
                {"type": "task_complete", "turn_id": "turn-1", "last_agent_message": "hi"},
            ),
        ]
        _write_jsonl(log, events)

        records = _replay(log)
    finally:
        Flowcept.campaign_id = original_campaign_id

    assert all(record.get("campaign_id") == "campaign-test" for record in _workflows(records))
    assert all(record.get("campaign_id") == "campaign-test" for record in _tasks(records))
    assert all(record.get("campaign_id") == "campaign-test" for record in records if record.get("type") == "agent")
