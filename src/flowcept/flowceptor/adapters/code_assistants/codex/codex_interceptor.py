"""Codex session log interceptor."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import sleep, time
from typing import Any

from flowcept.commons.flowcept_dataclasses.agent_object import AgentObject
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.flowcept_dataclasses.workflow_object import WorkflowObject
from flowcept.commons.utils import get_utc_now
from flowcept.commons.vocabulary import PROV_AGENT, PROV_AGENT_LOOP, Status
from flowcept.flowceptor.adapters.base_interceptor import BaseInterceptor


JsonObject = dict[str, Any]

PLAN_SUMMARY_SECTION_NAMES = {
    "resumo",
    "summary",
}

PLAN_EVALUATION_SECTION_NAMES = {
    "verificacao",
    "verificacoes",
    "verification",
    "verifications",
    "validation",
    "validacao",
    "test",
    "tests",
    "testing",
    "teste",
    "testes",
    "evaluation",
    "avaliacao",
    "evaluation_criteria",
    "criterios_de_avaliacao",
    "criterios_avaliacao",
}

PLAN_STEP_SECTION_NAMES = {
    "steps",
    "step",
    "etapas",
    "etapa",
    "passos",
    "passo",
}

FLOWCEPT_MESSAGE_EVENT_TYPES = {
    "user_prompt",
    "agent_response",
    "thought",
    "observation",
    "belief",
    "decision",
    "mandate",
    "message",
    "checkpoint",
    "memory",
    "lesson_learned",
}

FLOWCEPT_ENTITY_EVENT_TYPES = {
    "objective",
    "plan",
    "checkpoint",
    "evaluation_criteria",
    "evaluation_result",
}

FLOWCEPT_TASK_EVENT_TYPES = {
    "plan_step_started",
    "plan_step_finished",
    "loop_iteration_started",
    "loop_iteration_finished",
    "evaluation_started",
    "evaluation_finished",
}

DPL_MESSAGE_CLASSES = {
    "Thought",
    "Observation",
    "Belief",
    "Decision",
    "Mandate",
    "Memory",
    "LessonLearned",
}

DPL_ENTITY_CLASSES = {
    "Objective",
    "Plan",
    "Checkpoint",
    "EvaluationCriteria",
    "EvaluationResult",
}

DPL_TASK_CLASSES = {
    "PlanStepExecution",
    "LoopIteration",
    "Evaluation",
}

DPL_CLASS_TO_MESSAGE_TYPE = {
    "Thought": "thought",
    "Observation": "observation",
    "Belief": "belief",
    "Decision": "decision",
    "Mandate": "mandate",
    "Memory": "memory",
    "LessonLearned": "lesson_learned",
}

DPL_CLASS_TO_ENTITY_TYPE = {
    "Objective": "objective",
    "Plan": "plan",
    "Checkpoint": "checkpoint",
    "EvaluationCriteria": "evaluation_criteria",
    "EvaluationResult": "evaluation_result",
}

DPL_CLASS_TO_TASK_PREFIX = {
    "PlanStepExecution": "plan_step",
    "LoopIteration": "loop_iteration",
    "Evaluation": "evaluation",
}

DPL_CLASS_ALIASES = {
    "thought": "Thought",
    "observation": "Observation",
    "belief": "Belief",
    "decision": "Decision",
    "mandate": "Mandate",
    "memory": "Memory",
    "lessonlearned": "LessonLearned",
    "objective": "Objective",
    "plan": "Plan",
    "checkpoint": "Checkpoint",
    "evaluationcriteria": "EvaluationCriteria",
    "evaluationcriterion": "EvaluationCriteria",
    "evaluationresult": "EvaluationResult",
    "planstepexecution": "PlanStepExecution",
    "planstep": "PlanStepExecution",
    "loopiteration": "LoopIteration",
    "evaluation": "Evaluation",
}

TOOL_DATA_SCHEDULING_PATTERNS = re.compile(
    r"\b("
    r"slurm|sbatch|squeue|sacct|scontrol|scancel|sstat|qsub|qstat|qdel|pbs|lsf|bsub|bjobs|job_id|"
    r"allocation|accounting|node-hours?|queue|partition"
    r")\b",
    re.IGNORECASE,
)

TOOL_DATA_TELEMETRY_PATTERNS = re.compile(
    r"\b("
    r"telemetry|nvidia-smi|rocm-smi|amd-smi|amdsmi|gpu|cpu|memory|mem|ram|vram|utilization|"
    r"power|energy|temperature|throughput|latency|iostat|vmstat|top|psutil"
    r")\b",
    re.IGNORECASE,
)


@dataclass
class ToolInvocationState:
    """State for a Codex function_call/function_call_output pair."""

    call_id: str
    task_id: str
    tool_name: str | None
    arguments: Any
    started_at: float | None
    workflow_id: str | None = None
    parent_task_id: str | None = None
    response_item_id: str | None = None
    ended_at: float | None = None
    output: Any = None
    emitted: bool = False


@dataclass
class TaggedTaskState:
    """State for explicit flowcept_event start/finish task boundaries."""

    task_id: str
    subtype: str
    activity_id: str
    workflow_id: str | None
    parent_task_id: str | None
    agent_id: str | None
    source_agent_id: str | None
    started_at: float | None
    used_messages: list[JsonObject] = field(default_factory=list)
    used_entities: list[JsonObject] = field(default_factory=list)
    generated_messages: list[JsonObject] = field(default_factory=list)
    generated_entities: list[JsonObject] = field(default_factory=list)
    metadata: JsonObject = field(default_factory=dict)
    emitted_started: bool = False


@dataclass
class ModelInvocationState:
    """State for a Codex model invocation within a turn."""

    task_id: str
    turn_id: str
    workflow_id: str | None
    parent_task_id: str | None
    agent_id: str | None
    source_agent_id: str | None
    started_at: float | None
    prompt: str | None = None
    ai_model: JsonObject = field(default_factory=dict)
    messages: list[JsonObject] = field(default_factory=list)
    used_entities: list[JsonObject] = field(default_factory=list)
    generated_messages: list[JsonObject] = field(default_factory=list)
    generated_entities: list[JsonObject] = field(default_factory=list)
    plans: list[JsonObject] = field(default_factory=list)
    response: str | None = None
    token_usage: JsonObject | None = None
    ended_at: float | None = None
    tools: dict[str, ToolInvocationState] = field(default_factory=dict)
    emitted_started: bool = False
    emitted: bool = False


@dataclass
class TurnState:
    """State for one Codex turn, mapped to a loop iteration."""

    task_id: str
    workflow_id: str | None
    agent_id: str | None
    source_agent_id: str | None
    started_at: float | None
    submitted_at: float | None = None
    ended_at: float | None = None
    prompt: str | None = None
    final_response: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    mandates: list[JsonObject] = field(default_factory=list)
    messages: list[JsonObject] = field(default_factory=list)
    invocations: list[ModelInvocationState] = field(default_factory=list)
    current_invocation: ModelInvocationState | None = None
    emitted: bool = False


def _compact_dict(data: JsonObject) -> JsonObject:
    return {key: value for key, value in data.items() if value is not None}


def _epoch_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _parse_json_or_raw(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _message_text(payload: JsonObject) -> str | None:
    content = payload.get("content") or []
    parts = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if text:
                parts.append(text)
    return "\n".join(parts) if parts else None


def _extract_proposed_plans(text: str | None) -> list[str]:
    if not text:
        return []
    return [
        match.group(1).strip()
        for match in re.finditer(r"<proposed_plan>(.*?)</proposed_plan>", text, flags=re.DOTALL)
        if match.group(1).strip()
    ]


def _extract_flowcept_events(text: str | None) -> list[JsonObject]:
    if not text:
        return []
    text = re.sub(r"<skill>.*?</skill>", "", text, flags=re.DOTALL)
    events = []
    for match in re.finditer(r"<flowcept_event>(.*?)</flowcept_event>", text, flags=re.DOTALL):
        raw_event = match.group(1).strip()
        if not raw_event:
            continue
        try:
            event = json.loads(raw_event)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and (event.get("type") or (event.get("layer") == "DPL" and event.get("class"))):
            events.append(event)
    return events


def _normalize_declared_event(event: JsonObject) -> JsonObject | None:
    if event.get("layer") == "DPL" and event.get("class"):
        raw_class = str(event.get("class") or "")
        class_key = re.sub(r"[\s_-]+", "", raw_class).lower()
        event_class = DPL_CLASS_ALIASES.get(class_key, raw_class)
        event_name = event.get("event")
        if event_class in DPL_MESSAGE_CLASSES:
            normalized = {key: value for key, value in event.items() if key not in {"layer", "class", "event"}}
            normalized["type"] = DPL_CLASS_TO_MESSAGE_TYPE[event_class]
            normalized["classification_source"] = "declared"
            return normalized
        if event_class in DPL_ENTITY_CLASSES:
            normalized = {key: value for key, value in event.items() if key not in {"layer", "class", "event"}}
            normalized["type"] = DPL_CLASS_TO_ENTITY_TYPE[event_class]
            normalized["classification_source"] = "declared"
            return normalized
        if event_class in DPL_TASK_CLASSES and event_name in {"started", "finished"}:
            normalized = {key: value for key, value in event.items() if key not in {"layer", "class", "event"}}
            normalized["type"] = f"{DPL_CLASS_TO_TASK_PREFIX[event_class]}_{event_name}"
            normalized["classification_source"] = "declared"
            return normalized
        return None
    if event.get("type"):
        normalized = dict(event)
        normalized.setdefault("classification_source", "declared")
        return normalized
    return None


def _strip_flowcept_events(text: str | None) -> str | None:
    if text is None:
        return None
    stripped = re.sub(r"<flowcept_event>.*?</flowcept_event>", "", text, flags=re.DOTALL).strip()
    return stripped or None


def _is_flowcept_event_only_text(text: str | None) -> bool:
    return bool(_extract_flowcept_events(text)) and _strip_flowcept_events(text) is None


def _normalize_plan_content(content: str | None) -> str | None:
    if content is None:
        return None
    return content.strip()


def _normalized_section_name(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name.strip().lower())
    ascii_name = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_name).strip("_")


def _parse_plan_content(content: str) -> JsonObject:
    title = None
    current_section = None
    sections: dict[str, list[str]] = {}
    raw_sections: dict[str, str] = {}

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.fullmatch(r"\*\*(.+?)\*\*", line)
        if heading:
            heading_text = heading.group(1).strip()
            if title is None:
                title = heading_text
                continue
            current_section = _normalized_section_name(heading_text)
            raw_sections[current_section] = heading_text
            sections.setdefault(current_section, [])
            continue
        if current_section is None:
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", line)
        sections[current_section].append((bullet.group(1) if bullet else line).strip())

    return _compact_dict(
        {
            "title": title,
            "sections": {key: value for key, value in sections.items() if value},
            "section_names": raw_sections or None,
        }
    )


def _section_items(sections: JsonObject, aliases: set[str]) -> list[str]:
    items = []
    for name, section_items in sections.items():
        if name in aliases:
            items.extend(section_items)
    return items


def _plan_summary(plan: JsonObject) -> str | None:
    summary_items = _section_items(plan.get("sections") or {}, PLAN_SUMMARY_SECTION_NAMES)
    return "\n".join(summary_items) if summary_items else None


def _canonical_plan_step_label(label: str | None) -> str | None:
    if not label:
        return None
    label = label.strip()
    backtick = re.match(r"`([^`]+)`", label)
    if backtick:
        label = backtick.group(1)
    label = re.sub(r"^\*\*(.+?)\*\*$", r"\1", label).strip()
    normalized = unicodedata.normalize("NFKD", label.lower())
    ascii_label = "".join(char for char in normalized if not unicodedata.combining(char))
    canonical = re.sub(r"[^a-z0-9]+", " ", ascii_label).strip()
    return canonical or None


def _plan_step_labels(plan: JsonObject) -> set[str]:
    content = plan.get("content")
    if not isinstance(content, str):
        return set()
    current_section = None
    labels: set[str] = set()
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        heading = re.fullmatch(r"\*\*(.+?)\*\*", stripped)
        if heading:
            current_section = _normalized_section_name(heading.group(1))
            continue
        if current_section not in PLAN_STEP_SECTION_NAMES:
            continue
        bullet = re.match(r"^[-*]\s+(.*)$", raw_line)
        if not bullet:
            continue
        label = _canonical_plan_step_label(bullet.group(1))
        if label:
            labels.add(label)
    return labels


def _task_status(ended_at: float | None, output: Any = None) -> Status:
    if ended_at is None:
        return Status.UNKNOWN
    if isinstance(output, str):
        exit_codes = re.findall(r"Process exited with code (\d+)", output)
        if exit_codes and any(code != "0" for code in exit_codes):
            return Status.ERROR
        if '"interrupted":true' in output or "'interrupted': True" in output:
            return Status.ERROR
    if isinstance(output, dict) and (output.get("interrupted") or output.get("is_error")):
        return Status.ERROR
    return Status.FINISHED


def _entity(kind: str, **kwargs) -> JsonObject:
    return _compact_dict({"type": kind, **kwargs})


def _message(content: str | None, attributed_to: str | None, role: str | None = None, **kwargs) -> JsonObject:
    return _entity("message", content=content, attributed_to=attributed_to, role=role, **kwargs)


def _thought(content: str | None, attributed_to: str | None, role: str | None = None, **kwargs) -> JsonObject:
    return _entity("thought", content=content, attributed_to=attributed_to, role=role, **kwargs)


def _mandate(content: str | None, attributed_to: str | None, role: str | None = None, **kwargs) -> JsonObject:
    return _entity("mandate", content=content, attributed_to=attributed_to, role=role, **kwargs)


def _is_context_message(content: str | None) -> bool:
    if content is None:
        return False
    stripped = content.strip()
    return stripped.startswith("<environment_context>") or stripped.startswith("<permissions instructions>")


def _is_injected_context_message(content: str | None) -> bool:
    if content is None:
        return False
    stripped = content.strip()
    return (
        stripped.startswith("<skill>")
        or stripped.startswith("<recommended_plugins>")
        or stripped.startswith("<turn_aborted>")
    )


class CodexInterceptor(BaseInterceptor):
    """Interceptors Codex JSONL session logs into Flowcept provenance records."""

    def __init__(self, plugin_key: str = "codex"):
        super().__init__(plugin_key)
        self._observer: Any | None = None
        self._processed_lines: dict[str, int] = {}
        self._session_id: str | None = None
        self._codex_agent_id: str | None = None
        self._human_agent_id: str | None = None
        self._model_provider: str | None = None
        self._current_turn_id: str | None = None
        self._active_execution_plan_workflow_id: str | None = None
        self._pending_execution_plan_workflow_id: str | None = None
        self._pending_execution_plan_turn_id: str | None = None
        self._execution_plan_criteria: dict[str, list[JsonObject]] = {}
        self._execution_plan_steps: dict[str, set[str]] = {}
        self._execution_plan_finished_steps: dict[str, set[str]] = {}
        self._tagged_task_counts: dict[str, int] = {}
        self._active_tagged_tasks: dict[tuple[str, str], TaggedTaskState] = {}
        self._processed_declared_events: set[str] = set()
        self._emitted_task_bounds: dict[str, tuple[float | None, float | None]] = {}
        self._turns: dict[str, TurnState] = {}
        self._emitted_records_count = 0

    def callback(self) -> int:
        """Read newly appended Codex JSONL events and emit Flowcept messages."""
        sleep(self.settings.watch_interval_sec)
        intercepted = 0
        for path in self._log_paths():
            intercepted += self._process_log(path)
        return intercepted

    def intercept(self, obj_msg: JsonObject):
        """Intercept and count emitted Codex provenance records."""
        obj_msg.setdefault("custom_metadata", {})
        if isinstance(obj_msg["custom_metadata"], dict):
            obj_msg["custom_metadata"].setdefault("flowcept_capture_observed_at", time())
        super().intercept(obj_msg)
        self._emitted_records_count += 1

    def start(self, bundle_exec_id, check_safe_stops: bool = True) -> "CodexInterceptor":
        """Start observing Codex logs."""
        super().start(bundle_exec_id, check_safe_stops)
        self.observe()
        return self

    def stop(self, check_safe_stops: bool = True) -> bool:
        """Stop observing Codex logs."""
        self.logger.debug("Codex interceptor stopping...")
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=1)
        try:
            self.callback()
            self._flush_open_records()
        except Exception as e:
            self.logger.exception(e)
        super().stop(check_safe_stops)
        self.logger.debug("Codex interceptor stopped.")
        return True

    def observe(self):
        """Observe Codex log files."""
        from watchdog.observers.polling import PollingObserver

        from flowcept.flowceptor.adapters.mlflow.interception_event_handler import (
            InterceptionEventHandler,
        )

        watch_path = Path(self.settings.file_path)
        parent_to_watch = watch_path if watch_path.is_dir() else watch_path.parent
        while not parent_to_watch.exists():
            self.logger.debug(f"I can't watch {parent_to_watch}, as it does not exist.")
            sleep(self.settings.watch_interval_sec)

        event_handler = InterceptionEventHandler(self, str(parent_to_watch), self.__class__.callback)
        self._observer = PollingObserver()
        self._observer.schedule(event_handler, str(parent_to_watch), recursive=self.settings.recursive)
        self._observer.start()
        sleep(0.2)
        self.logger.debug(f"Watching Codex logs under {parent_to_watch}")
        self.callback()

    def _log_paths(self) -> list[Path]:
        path = Path(self.settings.file_path)
        if path.is_file():
            return [path]
        if not path.exists():
            return []
        if path.is_dir():
            return sorted(item for item in path.rglob("*.jsonl") if item.is_file())
        return []

    def _process_log(self, path: Path) -> int:
        path_key = str(path.resolve())
        processed = self._processed_lines.get(path_key, 0)
        intercepted_before = self._emitted_records_count
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if line_number <= processed:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    self.logger.warning(f"Skipping invalid Codex JSONL line {line_number} in {path}: {exc}")
                    continue
                self._map_event(event, line_number, path)
                self._processed_lines[path_key] = line_number
        return self._emitted_records_count - intercepted_before

    def _map_event(self, event: JsonObject, line_number: int, path: Path):
        event_type = event.get("type")
        payload = event.get("payload") or {}
        timestamp = _epoch_seconds(event.get("timestamp"))
        if event_type == "session_meta":
            self._handle_session_meta(payload, timestamp, line_number, path)
        elif event_type == "turn_context":
            self._handle_turn_context(payload)
        elif event_type == "event_msg":
            self._handle_event_msg(payload, timestamp, line_number)
        elif event_type == "response_item":
            self._handle_response_item(payload, timestamp, line_number)

    def _handle_session_meta(self, payload: JsonObject, timestamp: float | None, line_number: int, path: Path):
        session_id = payload.get("session_id") or payload.get("id")
        if not session_id:
            return
        self._session_id = session_id
        self._codex_agent_id = f"codex:{session_id}"
        self._human_agent_id = f"human:{session_id}"
        self._model_provider = payload.get("model_provider")

        workflow_obj = WorkflowObject(workflow_id=session_id, name=payload.get("title") or session_id)
        workflow_obj.subtype = PROV_AGENT_LOOP.SESSION.value
        workflow_obj.campaign_id = self._campaign_id()
        workflow_obj.started_at = _epoch_seconds(payload.get("timestamp")) or timestamp
        workflow_obj.status = Status.UNKNOWN
        workflow_obj.used = {
            "entities": [
                _entity(
                    "mandate",
                    content=(payload.get("base_instructions") or {}).get("text"),
                    attributed_to=self._human_agent_id,
                )
            ]
        }
        workflow_obj.workflow_description = "Codex session imported from a Codex JSONL transcript."
        self._send_workflow_message(workflow_obj)
        self.send_agent_message(self._agent_obj(self._codex_agent_id, payload.get("originator") or "Codex"))
        self.send_agent_message(self._agent_obj(self._human_agent_id, "Human"))

    def _handle_turn_context(self, payload: JsonObject):
        turn_id = payload.get("turn_id") or self._current_turn_id
        turn = self._turns.get(turn_id) if turn_id else None
        if not turn:
            return
        collaboration_mode = payload.get("collaboration_mode") or {}
        sandbox_policy = payload.get("sandbox_policy") or {}
        turn.metadata.update(
            _compact_dict(
                {
                    "turn_id": turn_id,
                    "cwd": payload.get("cwd"),
                    "model": payload.get("model"),
                    "effort": payload.get("effort"),
                    "approval_policy": payload.get("approval_policy"),
                    "sandbox_policy": sandbox_policy,
                    "collaboration_mode_kind": collaboration_mode.get("mode"),
                    "workspace_roots": payload.get("workspace_roots"),
                    "current_date": payload.get("current_date"),
                    "timezone": payload.get("timezone"),
                }
            )
        )
        for invocation in turn.invocations:
            self._apply_model_metadata(invocation, turn)

    def _handle_event_msg(self, payload: JsonObject, timestamp: float | None, line_number: int):
        payload_type = payload.get("type")
        if payload_type == "task_started":
            self._start_turn(payload, timestamp, line_number)
        elif payload_type == "user_message":
            self._set_turn_prompt(payload.get("message"), timestamp)
        elif payload_type == "agent_message":
            if payload.get("phase") == "final_answer":
                turn = self._current_turn()
                if turn:
                    turn.final_response = _strip_flowcept_events(payload.get("message")) or turn.final_response
                return
            turn = self._current_turn()
            if _is_flowcept_event_only_text(payload.get("message")) and turn and not turn.current_invocation:
                if self.settings.declared_provenance_enabled:
                    self._handle_declared_annotation_text(payload.get("message"), timestamp)
                return
            invocation = self._ensure_invocation(timestamp)
            if invocation:
                self._add_assistant_text(invocation, payload.get("message"), payload.get("phase"), timestamp)
        elif payload_type == "item_completed":
            self._handle_item_completed(payload, timestamp)
        elif payload_type == "token_count":
            self._close_invocation_with_tokens(payload, timestamp)
        elif payload_type == "task_complete":
            self._complete_turn(payload, timestamp, line_number)
        elif payload_type == "turn_aborted":
            self._abort_turn(payload, timestamp, line_number)

    def _handle_response_item(self, payload: JsonObject, timestamp: float | None, line_number: int):
        metadata = payload.get("internal_chat_message_metadata_passthrough") or {}
        turn_id = metadata.get("turn_id")
        if turn_id in self._turns:
            self._current_turn_id = turn_id

        payload_type = payload.get("type")
        if payload_type == "message":
            self._handle_message(payload, timestamp, line_number)
        elif payload_type == "reasoning" and self.settings.include_reasoning:
            invocation = self._ensure_invocation(timestamp)
            if invocation:
                self._append_unique_message(
                    invocation.generated_messages,
                    _entity(
                        "thought",
                        content=payload.get("summary") or payload.get("content"),
                        encrypted_content=payload.get("encrypted_content"),
                        attributed_to=invocation.agent_id,
                    ),
                )
        elif payload_type == "function_call":
            self._handle_function_call(payload, timestamp)
        elif payload_type == "function_call_output":
            self._handle_function_call_output(payload, timestamp)
        elif payload_type == "custom_tool_call":
            self._handle_custom_tool_call(payload, timestamp)
        elif payload_type == "custom_tool_call_output":
            self._handle_function_call_output(payload, timestamp)

    def _start_turn(self, payload: JsonObject, timestamp: float | None, line_number: int):
        turn_id = payload.get("turn_id")
        if not turn_id:
            return
        self._current_turn_id = turn_id
        started_at = _epoch_seconds(payload.get("started_at")) or timestamp
        turn = TurnState(
            task_id=turn_id,
            workflow_id=self._session_id,
            agent_id=self._codex_agent_id,
            source_agent_id=self._human_agent_id,
            started_at=started_at,
            metadata=_compact_dict(
                {
                    "turn_id": turn_id,
                    "collaboration_mode_kind": payload.get("collaboration_mode_kind"),
                    "model_context_window": payload.get("model_context_window"),
                    "line_number": line_number,
                }
            ),
        )
        self._turns[turn_id] = turn

    def _set_turn_prompt(self, prompt: str | None, timestamp: float | None):
        turn = self._current_turn()
        if not turn or prompt is None:
            return
        if _is_injected_context_message(prompt):
            return
        if _is_context_message(prompt):
            mandate = _mandate(prompt, attributed_to=turn.agent_id, role="user")
            self._append_unique_message(turn.mandates, mandate)
            if turn.current_invocation:
                self._append_unique_message(turn.current_invocation.messages, mandate)
            return
        turn.prompt = prompt
        turn.submitted_at = timestamp
        message = _entity("user_prompt", content=prompt, attributed_to=turn.source_agent_id, role="user")
        self._append_unique_message(turn.messages, message)
        invocation = self._ensure_invocation(timestamp)
        if invocation and (invocation.prompt is None or _is_context_message(invocation.prompt)):
            invocation.prompt = prompt
            self._append_unique_message(invocation.messages, message)

    def _handle_message(self, payload: JsonObject, timestamp: float | None, line_number: int):
        role = payload.get("role")
        text = _message_text(payload)
        if not text:
            return
        turn = self._current_turn()
        if role == "user":
            self._set_turn_prompt(text, timestamp)
        elif role == "developer" and self.settings.include_developer_messages and turn:
            if _is_context_message(text):
                mandate = _mandate(text, attributed_to=turn.agent_id, role=role)
                self._append_unique_message(turn.mandates, mandate)
                if turn.current_invocation:
                    self._append_unique_message(turn.current_invocation.messages, mandate)
            else:
                message = _message(
                    text,
                    attributed_to=turn.source_agent_id,
                    role=role,
                )
                self._append_unique_message(turn.messages, message)
                if turn.current_invocation:
                    self._append_unique_message(turn.current_invocation.messages, message)
        elif role == "assistant":
            if _is_flowcept_event_only_text(text) and turn and not turn.current_invocation:
                if self.settings.declared_provenance_enabled:
                    self._handle_declared_annotation_text(text, timestamp)
                return
            invocation = self._ensure_invocation(timestamp)
            if invocation:
                self._add_assistant_text(invocation, text, payload.get("phase"), timestamp)

    def _handle_item_completed(self, payload: JsonObject, timestamp: float | None):
        item = payload.get("item") or {}
        if item.get("type") != "Plan":
            return
        invocation = self._ensure_invocation(timestamp)
        if invocation:
            self._register_plan(
                invocation,
                content=item.get("text"),
                item_id=item.get("id"),
                timestamp=timestamp,
            )

    def _add_assistant_text(
        self,
        invocation: ModelInvocationState,
        text: str | None,
        phase: str | None,
        timestamp: float | None,
    ):
        if not text:
            return
        if self.settings.declared_provenance_enabled:
            for event in _extract_flowcept_events(text):
                self._handle_flowcept_event(invocation, event, timestamp)
        clean_text = _strip_flowcept_events(text)
        for plan_text in _extract_proposed_plans(text):
            self._register_plan(invocation, content=plan_text, item_id=None, timestamp=timestamp)
        if phase == "final_answer":
            invocation.response = clean_text
            invocation.ended_at = timestamp or invocation.ended_at
        elif clean_text:
            message = _thought(clean_text, attributed_to=invocation.agent_id, role="assistant", phase=phase)
            self._append_unique_message(invocation.generated_messages, message)
        turn = self._turns.get(invocation.turn_id)
        close_at = turn.metadata.pop("close_current_invocation_at", None) if turn else None
        if close_at and turn and turn.current_invocation is invocation and not invocation.emitted:
            invocation.ended_at = close_at
            turn.current_invocation = None

    def _handle_declared_annotation_text(self, text: str | None, timestamp: float | None):
        turn = self._current_turn()
        if not turn:
            return
        invocation = self._last_invocation(turn)
        if not invocation:
            return
        for event in _extract_flowcept_events(text):
            self._handle_flowcept_event(invocation, event, timestamp)

    def _handle_flowcept_event(
        self,
        invocation: ModelInvocationState,
        event: JsonObject,
        timestamp: float | None,
    ):
        event = _normalize_declared_event(event)
        if not event:
            return
        event_key = json.dumps(
            {
                "turn_id": invocation.turn_id,
                "event": event,
            },
            sort_keys=True,
            default=str,
        )
        if event_key in self._processed_declared_events:
            return
        self._processed_declared_events.add(event_key)
        event_type = event.get("type")
        if event_type in {"user_prompt", "agent_response"}:
            return
        if event_type in FLOWCEPT_MESSAGE_EVENT_TYPES:
            self._handle_flowcept_message_event(invocation, event)
        elif event_type in FLOWCEPT_ENTITY_EVENT_TYPES:
            self._handle_flowcept_entity_event(invocation, event)
        elif event_type in FLOWCEPT_TASK_EVENT_TYPES:
            self._handle_flowcept_task_event(invocation, event, timestamp)

    def _handle_flowcept_message_event(self, invocation: ModelInvocationState, event: JsonObject):
        event_type = event.get("type")
        attributed_to = self._event_attributed_to(event, invocation)
        message = _entity(
            event_type,
            **_compact_dict(
                {
                    ("content" if key == "summary" and "content" not in event else key): value
                    for key, value in event.items()
                    if key not in {"type", "attributed_to"}
                }
            ),
            attributed_to=attributed_to,
        )
        if event_type == "user_prompt" and "role" not in message:
            message["role"] = "user"
        elif event_type == "agent_response" and "role" not in message:
            message["role"] = "assistant"
        if event_type == "user_prompt":
            invocation.prompt = event.get("content") or invocation.prompt
            self._append_unique_message(invocation.messages, message)
            turn = self._turns.get(invocation.turn_id)
            if turn:
                turn.prompt = event.get("content") or turn.prompt
                self._append_unique_message(turn.messages, message)
        elif event_type in {"mandate", "objective"}:
            self._append_unique_message(invocation.messages, message)
            turn = self._turns.get(invocation.turn_id)
            if turn and event_type == "mandate":
                self._append_unique_message(turn.mandates, message)
            elif turn:
                self._append_unique_message(turn.messages, message)
        elif event_type == "agent_response":
            invocation.response = event.get("content") or invocation.response
            turn = self._turns.get(invocation.turn_id)
            if turn:
                turn.final_response = event.get("content") or turn.final_response
        else:
            if not invocation.emitted:
                self._append_unique_message(invocation.generated_messages, message)
            else:
                self._append_declared_entity_to_active_context(invocation, message, event_type)

    def _handle_flowcept_entity_event(self, invocation: ModelInvocationState, event: JsonObject):
        event_type = event.get("type")
        entity = _entity(
            event_type,
            **_compact_dict(
                {
                    ("content" if key == "summary" and "content" not in event else key): value
                    for key, value in event.items()
                    if key != "type"
                }
            ),
            attributed_to=self._event_attributed_to(event, invocation),
        )
        if event_type == "plan" and entity.get("content"):
            self._register_plan(
                invocation,
                content=entity.get("content"),
                item_id=entity.get("item_id"),
                timestamp=invocation.started_at,
            )
            return
        if not invocation.emitted:
            self._append_unique_message(invocation.generated_entities, entity)
        else:
            self._append_declared_entity_to_active_context(invocation, entity, event_type)

    def _handle_flowcept_task_event(
        self,
        invocation: ModelInvocationState,
        event: JsonObject,
        timestamp: float | None,
    ):
        event_type = event.get("type")
        if event_type.endswith("_started"):
            self._start_tagged_task(invocation, event, timestamp)
        elif event_type.endswith("_finished"):
            self._finish_tagged_task(invocation, event, timestamp)

    def _start_tagged_task(
        self,
        invocation: ModelInvocationState,
        event: JsonObject,
        timestamp: float | None,
    ):
        subtype, activity_id = self._tagged_task_kind(event["type"])
        key = self._tagged_task_key(event)
        if key in self._active_tagged_tasks:
            return
        workflow_id = self._workflow_for_tagged_task(invocation, subtype)
        if subtype == PROV_AGENT_LOOP.LOOP_ITERATION.value:
            self._start_observed_loop_context(invocation, event, workflow_id, timestamp)
            return
        started_at = timestamp or invocation.started_at
        if started_at is not None and subtype == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value:
            started_at -= 0.002
        parent_task_id = self._parent_for_tagged_task(subtype)
        if started_at is not None and subtype == PROV_AGENT_LOOP.EVALUATION.value and parent_task_id is not None:
            parent = self._active_tagged_task(PROV_AGENT_LOOP.LOOP_ITERATION.value)
            if parent and parent.task_id == parent_task_id and parent.started_at is not None:
                started_at = max(started_at, parent.started_at + 0.001)
        task = TaggedTaskState(
            task_id=self._next_tagged_task_id(invocation, subtype),
            subtype=subtype,
            activity_id=activity_id,
            workflow_id=workflow_id,
            parent_task_id=parent_task_id,
            agent_id=invocation.agent_id,
            source_agent_id=invocation.source_agent_id,
            started_at=started_at,
            used_messages=self._tagged_task_used_messages(event, invocation, subtype, workflow_id),
            used_entities=self._tagged_task_used_entities(event, invocation, subtype, workflow_id),
            metadata=self._tagged_task_metadata(event, invocation),
        )
        self._active_tagged_tasks[key] = task
        self._remember_tagged_context(invocation, task)
        self._emit_tagged_task(task, timestamp, final=False)

    def _finish_tagged_task(
        self,
        invocation: ModelInvocationState,
        event: JsonObject,
        timestamp: float | None,
    ):
        start_type = event["type"].replace("_finished", "_started")
        key = self._tagged_task_key({**event, "type": start_type})
        state = self._active_tagged_tasks.pop(key, None)
        if state is not None and state.metadata.get("observed_loop_iteration"):
            self._finish_observed_loop_context(invocation, event, state, timestamp)
            return
        if state is None:
            subtype, activity_id = self._tagged_task_kind(event["type"])
            workflow_id = self._workflow_for_tagged_task(invocation, subtype)
            if subtype == PROV_AGENT_LOOP.LOOP_ITERATION.value:
                self._finish_observed_loop_context(invocation, event, None, timestamp)
                return
            state = TaggedTaskState(
                task_id=self._next_tagged_task_id(invocation, subtype),
                subtype=subtype,
                activity_id=activity_id,
                workflow_id=workflow_id,
                parent_task_id=self._parent_for_tagged_task(subtype),
                agent_id=invocation.agent_id,
                source_agent_id=invocation.source_agent_id,
                started_at=timestamp or invocation.started_at,
                used_messages=self._tagged_task_used_messages(event, invocation, subtype, workflow_id),
                used_entities=self._tagged_task_used_entities(event, invocation, subtype, workflow_id),
                metadata=self._tagged_task_metadata(event, invocation),
            )
        state.generated_messages.extend(self._tagged_task_generated_messages(event, invocation, state.subtype))
        state.generated_entities.extend(self._tagged_task_generated_entities(event, invocation, state.subtype))
        state.metadata.update(self._tagged_task_metadata(event, invocation))
        self._emit_tagged_task(state, timestamp, final=True)
        self._clear_finished_tagged_context(invocation, state, timestamp)

    def _emit_tagged_task(self, state: TaggedTaskState, timestamp: float | None, final: bool = True):
        if not final and state.emitted_started:
            return
        if not final and self._current_task_buffer() is None:
            return
        task = TaskObject()
        task.task_id = state.task_id
        task.workflow_id = state.workflow_id
        task.parent_task_id = state.parent_task_id
        task.campaign_id = self._campaign_id()
        task.agent_id = state.agent_id
        task.source_agent_id = state.source_agent_id
        task.subtype = state.subtype
        task.activity_id = state.metadata.get("label") or state.activity_id
        task.used = _compact_dict(
            {
                "entities": (state.used_messages + state.used_entities) or None,
            }
        )
        if final:
            task.generated = _compact_dict(
                {
                    "entities": (state.generated_messages + state.generated_entities) or None,
                }
            )
        task.started_at = state.started_at
        task.ended_at = (timestamp or state.started_at) if final else None
        task.utc_timestamp = task.started_at
        self._normalize_child_task_bounds(task)
        task.status = _task_status(task.ended_at, state.metadata.get("result")) if final else Status.RUNNING
        task.enrich(self.plugin_key)
        self._intercept_task(task)
        if not final:
            state.emitted_started = True

    def _handle_function_call(self, payload: JsonObject, timestamp: float | None):
        invocation = self._ensure_invocation(timestamp)
        if not invocation:
            return
        self._apply_active_context_to_invocation(invocation)
        self._emit_invocation_start(invocation)
        call_id = payload.get("call_id") or payload.get("id")
        if not call_id:
            return
        tool_name = payload.get("name")
        arguments = _parse_json_or_raw(payload.get("arguments"))
        invocation.tools[call_id] = ToolInvocationState(
            call_id=call_id,
            task_id=f"{invocation.task_id}:tool_invocation:{len(invocation.tools) + 1}",
            tool_name=tool_name,
            arguments=arguments,
            started_at=timestamp,
            workflow_id=invocation.workflow_id,
            parent_task_id=invocation.parent_task_id,
            response_item_id=payload.get("id"),
        )
        if tool_name == "update_plan":
            self._register_update_plan(invocation, arguments, timestamp)

    def _handle_custom_tool_call(self, payload: JsonObject, timestamp: float | None):
        invocation = self._ensure_invocation(timestamp)
        if not invocation:
            return
        self._apply_active_context_to_invocation(invocation)
        self._emit_invocation_start(invocation)
        call_id = payload.get("call_id") or payload.get("id")
        if not call_id:
            return
        invocation.tools[call_id] = ToolInvocationState(
            call_id=call_id,
            task_id=f"{invocation.task_id}:tool_invocation:{len(invocation.tools) + 1}",
            tool_name=payload.get("name") or "custom_tool_call",
            arguments=_parse_json_or_raw(payload.get("input")),
            started_at=timestamp,
            workflow_id=invocation.workflow_id,
            parent_task_id=invocation.parent_task_id,
            response_item_id=payload.get("id"),
            ended_at=timestamp if payload.get("status") == "completed" else None,
        )

    def _register_update_plan(
        self,
        invocation: ModelInvocationState,
        arguments: Any,
        timestamp: float | None,
    ):
        if self._active_execution_plan_workflow_id or self._pending_execution_plan_workflow_id:
            return
        if not isinstance(arguments, dict):
            return
        plan_items = arguments.get("plan")
        if not isinstance(plan_items, list) or not plan_items:
            return
        lines = ["**Execution Plan**", "", "**Steps**"]
        for item in plan_items:
            if not isinstance(item, dict) or not item.get("step"):
                continue
            lines.append(f"- `{item['step']}`")
        content = "\n".join(lines)
        self._register_plan(invocation, content=content, item_id="codex:update_plan", timestamp=timestamp)

    def _handle_function_call_output(self, payload: JsonObject, timestamp: float | None):
        call_id = payload.get("call_id")
        invocation = self._find_invocation_for_call(call_id) or self._ensure_invocation(timestamp)
        if not invocation or not call_id:
            return
        tool = invocation.tools.get(call_id)
        if tool is None:
            tool = ToolInvocationState(
                call_id=call_id,
                task_id=f"{invocation.task_id}:tool_invocation:{len(invocation.tools) + 1}",
                tool_name=None,
                arguments=None,
                started_at=timestamp,
                workflow_id=invocation.workflow_id,
                parent_task_id=invocation.parent_task_id,
            )
            invocation.tools[call_id] = tool
        tool.output = _parse_json_or_raw(payload.get("output"))
        tool.ended_at = timestamp
        self._emit_tool(tool, invocation)

    def _close_invocation_with_tokens(self, payload: JsonObject, timestamp: float | None):
        turn = self._current_turn()
        invocation = turn.current_invocation if turn else None
        if not invocation or not turn:
            return
        info = payload.get("info") or {}
        usage = info.get("last_token_usage") or info
        invocation.token_usage = self._normalize_llm_usage(usage, invocation, info)
        invocation.ai_model["context_window"] = info.get("model_context_window") or invocation.ai_model.get(
            "context_window"
        )
        invocation.ended_at = timestamp
        turn.current_invocation = None

    def _complete_turn(self, payload: JsonObject, timestamp: float | None, line_number: int):
        turn_id = payload.get("turn_id") or self._current_turn_id
        turn = self._turns.get(turn_id) if turn_id else None
        if not turn:
            return
        turn.final_response = _strip_flowcept_events(payload.get("last_agent_message"))
        turn.ended_at = _epoch_seconds(payload.get("completed_at")) or timestamp
        turn.metadata.update(
            _compact_dict(
                {
                    "duration_ms": payload.get("duration_ms"),
                    "time_to_first_token_ms": payload.get("time_to_first_token_ms"),
                    "line_number_completed": line_number,
                }
            )
        )
        response_invocation = self._last_unemitted_invocation(turn) or turn.current_invocation
        if response_invocation and turn.final_response:
            response_invocation.response = response_invocation.response or turn.final_response
        if turn.current_invocation:
            turn.current_invocation.ended_at = turn.current_invocation.ended_at or turn.ended_at
            turn.current_invocation = None
        for invocation in turn.invocations:
            if not invocation.emitted:
                invocation.ended_at = invocation.ended_at or turn.ended_at
                self._emit_invocation(invocation)
        self._discard_empty_started_tagged_tasks()
        self._emit_turn(turn)
        self._activate_pending_execution_plan(turn.task_id)
        self._current_turn_id = None

    def _abort_turn(self, payload: JsonObject, timestamp: float | None, line_number: int):
        turn_id = payload.get("turn_id") or self._current_turn_id
        turn = self._turns.get(turn_id) if turn_id else None
        if not turn:
            return
        turn.ended_at = _epoch_seconds(payload.get("completed_at")) or timestamp
        turn.metadata.update(
            _compact_dict(
                {
                    "interrupted": True,
                    "abort_reason": payload.get("reason"),
                    "line_number_aborted": line_number,
                }
            )
        )
        if turn.current_invocation:
            turn.current_invocation.ended_at = turn.current_invocation.ended_at or turn.ended_at
            if self._invocation_has_observed_work(turn.current_invocation):
                self._emit_invocation(turn.current_invocation)
            elif turn.current_invocation in turn.invocations:
                turn.invocations.remove(turn.current_invocation)
            turn.current_invocation = None
        self._discard_empty_started_tagged_tasks()
        self._emit_turn(turn)
        self._activate_pending_execution_plan(turn.task_id)
        self._current_turn_id = None

    def _ensure_invocation(self, timestamp: float | None) -> ModelInvocationState | None:
        turn = self._current_turn()
        if not turn:
            return None
        if turn.current_invocation:
            self._apply_active_context_to_invocation(turn.current_invocation)
            return turn.current_invocation
        self._emit_closed_invocations(turn)
        workflow_id = self._workflow_for_turn(turn)
        fallback_loop_id = turn.task_id if self._should_emit_fallback_loop(turn, workflow_id) else None
        invocation = ModelInvocationState(
            task_id=f"{turn.task_id}:ai_model_invocation:{len(turn.invocations) + 1}",
            turn_id=turn.task_id,
            workflow_id=workflow_id,
            parent_task_id=self._parent_for_observed_task(
                PROV_AGENT.AI_MODEL_INVOCATION.value,
                workflow_id=workflow_id,
                fallback=fallback_loop_id,
            ),
            agent_id=turn.agent_id,
            source_agent_id=turn.source_agent_id,
            started_at=timestamp or turn.started_at,
            prompt=turn.prompt,
            messages=list(turn.mandates + turn.messages),
        )
        self._apply_active_context_to_invocation(invocation)
        self._apply_model_metadata(invocation, turn)
        turn.invocations.append(invocation)
        turn.current_invocation = invocation
        return invocation

    def _last_unemitted_invocation(self, turn: TurnState) -> ModelInvocationState | None:
        for invocation in reversed(turn.invocations):
            if not invocation.emitted:
                return invocation
        return None

    def _last_invocation(self, turn: TurnState) -> ModelInvocationState | None:
        return turn.invocations[-1] if turn.invocations else None

    def _emit_closed_invocations(self, turn: TurnState):
        for invocation in turn.invocations:
            if not invocation.emitted and invocation.ended_at is not None:
                self._emit_invocation(invocation)

    def _apply_model_metadata(self, invocation: ModelInvocationState, turn: TurnState):
        invocation.ai_model.update(
            _compact_dict(
                {
                    "type": "ai_model",
                    "model": turn.metadata.get("model"),
                    "provider": self._workflow_provider(),
                    "effort": turn.metadata.get("effort"),
                    "context_window": turn.metadata.get("model_context_window"),
                }
            )
        )

    def _normalize_llm_usage(self, usage: JsonObject, invocation: ModelInvocationState, info: JsonObject) -> JsonObject:
        return _compact_dict(
            {
                "model": invocation.ai_model.get("model"),
                "input_tokens": usage.get("input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
                "model_context_window": info.get("model_context_window"),
                "token_count_source": "codex_token_count",
            }
        )

    def _emit_turn(self, turn: TurnState):
        if turn.emitted:
            return
        workflow_id = self._workflow_for_turn(turn)
        if not self._should_emit_fallback_loop(turn, workflow_id):
            turn.emitted = True
            return
        if not any(self._invocation_has_observed_work(invocation) for invocation in turn.invocations):
            turn.emitted = True
            return
        task = TaskObject()
        task.task_id = turn.task_id
        task.workflow_id = workflow_id
        task.parent_task_id = self._parent_for_observed_loop(turn)
        task.campaign_id = self._campaign_id()
        task.agent_id = turn.agent_id
        task.source_agent_id = turn.source_agent_id
        task.subtype = PROV_AGENT_LOOP.LOOP_ITERATION.value
        task.activity_id = "loop_iteration"
        if turn.metadata.get("declared_loop_label"):
            task.activity_id = turn.metadata.get("declared_loop_label")
        if turn.metadata.get("declared_loop_seen"):
            turn.emitted = True
            return
        task.used = _compact_dict(
            {
                "entities": (turn.mandates + turn.messages) or None,
            }
        )
        task.submitted_at = turn.submitted_at
        task.started_at = turn.metadata.get("declared_loop_started_at") or turn.started_at
        child_ended_at = [
            ended_at for invocation in turn.invocations for ended_at in [invocation.ended_at] if ended_at is not None
        ]
        task.ended_at = turn.metadata.get("declared_loop_finished_at") or max(
            [ended_at for ended_at in [turn.ended_at, *child_ended_at] if ended_at is not None],
            default=None,
        )
        task.utc_timestamp = task.started_at
        self._normalize_child_task_bounds(task)
        task.status = self._loop_iteration_status(task.ended_at, turn.metadata)
        task.enrich(self.plugin_key)
        self._intercept_task(task)
        turn.emitted = True

    def _emit_invocation(self, invocation: ModelInvocationState):
        if invocation.emitted:
            return
        if not self._invocation_has_observed_work(invocation):
            invocation.emitted = True
            return
        task = self._invocation_task(invocation, final=True)
        self._intercept_task(task)
        invocation.emitted_started = True
        invocation.emitted = True
        for tool in invocation.tools.values():
            if tool.ended_at is not None:
                self._emit_tool(tool, invocation)

    def _emit_invocation_start(self, invocation: ModelInvocationState):
        if invocation.emitted_started or invocation.emitted:
            return
        if self._current_task_buffer() is None:
            return
        if not self._invocation_has_observed_work(invocation):
            return
        task = self._invocation_task(invocation, final=False)
        self._intercept_task(task)
        invocation.emitted_started = True

    def _invocation_task(self, invocation: ModelInvocationState, final: bool):
        response = None
        if final:
            response = (
                invocation.response
                or self._response_from_generated_messages(invocation)
                or self._response_from_tool_requests(invocation)
            )
        task = TaskObject()
        task.task_id = invocation.task_id
        task.workflow_id = invocation.workflow_id
        task.parent_task_id = invocation.parent_task_id
        task.campaign_id = self._campaign_id()
        task.agent_id = invocation.agent_id
        task.source_agent_id = invocation.source_agent_id
        task.subtype = PROV_AGENT.AI_MODEL_INVOCATION.value
        task.activity_id = "ai_model_invocation"
        task.used = _compact_dict(
            {
                "prompt": invocation.prompt or self._prompt_from_messages(invocation.messages),
                "entities": (
                    invocation.messages
                    + invocation.used_entities
                    + ([invocation.ai_model] if invocation.ai_model else [])
                )
                or None,
            }
        )
        if final:
            task.generated = _compact_dict(
                {
                    "response": response,
                    "entities": (
                        self._generated_invocation_messages(invocation)
                        + self._generated_invocation_entities(invocation)
                    )
                    or None,
                }
            )
        task.started_at = invocation.started_at
        task.ended_at = invocation.ended_at if final else None
        task.utc_timestamp = task.started_at
        self._normalize_child_task_bounds(task)
        task.status = _task_status(invocation.ended_at) if final else Status.RUNNING
        if final:
            task.custom_metadata = _compact_dict(
                {
                    "llm_usage": invocation.token_usage,
                    "response_metadata": {
                        "model": invocation.ai_model.get("model"),
                        "provider": invocation.ai_model.get("provider"),
                        "effort": invocation.ai_model.get("effort"),
                        "context_window": invocation.ai_model.get("context_window"),
                    },
                }
            )
        task.enrich(self.plugin_key)
        return task

    def _response_from_generated_messages(self, invocation: ModelInvocationState) -> str | None:
        for message in reversed(invocation.generated_messages + invocation.generated_entities + invocation.plans):
            content = message.get("content")
            if content:
                return str(content)
        return None

    def _response_from_tool_requests(self, invocation: ModelInvocationState) -> str | None:
        if not invocation.tools:
            return None
        names = [tool.tool_name or "tool_invocation" for tool in invocation.tools.values()]
        if len(names) == 1:
            return f"Requested tool invocation: {names[0]}"
        return "Requested tool invocations: " + ", ".join(names)

    def _invocation_has_observed_work(self, invocation: ModelInvocationState) -> bool:
        return bool(
            invocation.tools
            or invocation.generated_messages
            or invocation.generated_entities
            or invocation.plans
            or invocation.response
            or invocation.token_usage
        )

    def _generated_invocation_messages(self, invocation: ModelInvocationState) -> list[JsonObject]:
        messages = []
        if invocation.response:
            messages.append(
                _entity(
                    "agent_response",
                    content=invocation.response,
                    attributed_to=invocation.agent_id,
                    role="assistant",
                )
            )
        messages.extend(invocation.generated_messages)
        return messages

    def _generated_invocation_entities(self, invocation: ModelInvocationState) -> list[JsonObject]:
        return list(invocation.generated_entities + invocation.plans)

    def _register_plan(
        self,
        invocation: ModelInvocationState,
        content: str | None,
        item_id: str | None,
        timestamp: float | None,
    ):
        content = _normalize_plan_content(content)
        if not content:
            return
        for existing in invocation.plans:
            if existing.get("content") == content:
                return
        plan = _entity(
            "plan",
            content=content,
            item_id=item_id,
            attributed_to=invocation.agent_id,
            generated_by=invocation.task_id,
            **_parse_plan_content(content),
        )
        invocation.plans.append(plan)
        self._emit_execution_plan(plan, invocation, timestamp)

    def _emit_execution_plan(
        self,
        plan: JsonObject,
        invocation: ModelInvocationState,
        timestamp: float | None,
    ):
        if self._active_execution_plan_workflow_id or self._pending_execution_plan_workflow_id:
            return
        workflow_id = f"{invocation.task_id}:execution_plan:{len(invocation.plans)}"
        workflow = WorkflowObject(
            workflow_id=workflow_id,
            name="execution_plan",
        )
        workflow.parent_workflow_id = self._session_id or invocation.workflow_id
        workflow.agent_id = invocation.agent_id
        workflow.campaign_id = self._campaign_id()
        workflow.subtype = PROV_AGENT_LOOP.EXECUTION_PLAN.value
        workflow.started_at = timestamp or invocation.started_at
        workflow.status = Status.RUNNING
        criteria = self._evaluation_criteria_from_plan(plan)
        if criteria:
            self._execution_plan_criteria[workflow_id] = criteria
        steps = _plan_step_labels(plan)
        if steps:
            self._execution_plan_steps[workflow_id] = steps
            self._execution_plan_finished_steps[workflow_id] = set()
        workflow.used = _compact_dict(
            {
                "entities": self._execution_plan_used_entities(plan, invocation, criteria) or None,
            }
        )
        workflow.workflow_description = (
            _plan_summary(plan) or "Codex execution plan extracted from a proposed_plan block or Plan item."
        )
        self._send_workflow_message(workflow)
        invocation.workflow_id = self._session_id or invocation.workflow_id
        turn = self._turns.get(invocation.turn_id)
        if turn:
            turn.metadata["produced_execution_plan_id"] = workflow_id
        self._pending_execution_plan_workflow_id = workflow_id
        self._pending_execution_plan_turn_id = invocation.turn_id

    def _execution_plan_used_entities(
        self,
        plan: JsonObject,
        invocation: ModelInvocationState,
        criteria: list[JsonObject],
    ) -> list[JsonObject]:
        entities = [
            _entity(
                "plan",
                content=plan.get("content"),
                title=plan.get("title"),
                sections=plan.get("sections") or None,
                item_id=plan.get("item_id"),
                attributed_to=plan.get("attributed_to"),
                generated_by=plan.get("generated_by"),
            )
        ]
        entities.extend(entity for entity in invocation.generated_entities if entity.get("type") == "objective")
        prompt = invocation.prompt or self._prompt_from_messages(invocation.messages)
        if prompt and not any(entity.get("type") == "objective" for entity in entities):
            entities.append(
                _entity(
                    "objective",
                    content=prompt,
                    attributed_to=invocation.source_agent_id,
                    role="user",
                )
            )
        return entities

    def _evaluation_criteria_from_plan(self, plan: JsonObject) -> list[JsonObject]:
        sections = plan.get("sections") or {}
        criteria = _section_items(sections, PLAN_EVALUATION_SECTION_NAMES)
        return [
            _entity(
                "evaluation_criteria",
                content=item,
                attributed_to=plan.get("attributed_to"),
                index=index,
            )
            for index, item in enumerate(criteria, start=1)
        ]

    def _emit_tool(self, tool: ToolInvocationState, invocation: ModelInvocationState):
        if tool.emitted:
            return
        task = TaskObject()
        task.task_id = tool.task_id
        task.workflow_id = tool.workflow_id or self._active_workflow_id(invocation.workflow_id)
        task.campaign_id = self._campaign_id()
        is_evaluation = self._is_test_command(tool.arguments)
        if is_evaluation and self._merge_tool_into_declared_evaluation(tool, invocation):
            return
        task.subtype = PROV_AGENT_LOOP.EVALUATION.value if is_evaluation else PROV_AGENT.TOOL_INVOCATION.value
        task.parent_task_id = self._parent_for_observed_task(
            task.subtype,
            workflow_id=task.workflow_id,
            fallback=tool.parent_task_id or invocation.parent_task_id,
        )
        task.agent_id = invocation.agent_id
        task.source_agent_id = invocation.source_agent_id
        task.activity_id = "evaluation" if is_evaluation else tool.tool_name or "tool_invocation"
        task.used = _compact_dict(
            {
                "entities": self._tool_used_entities(tool, task.workflow_id, is_evaluation) or None,
            }
        )
        task.generated = _compact_dict(
            {
                "entities": [
                    (
                        _entity(
                            "evaluation_result",
                            content=tool.output,
                            attributed_to=invocation.agent_id,
                            generated_by=tool.task_id,
                        )
                        if is_evaluation
                        else _entity(
                            self._tool_data_entity_type(tool, tool.output),
                            content=tool.output,
                            attributed_to=invocation.agent_id,
                            generated_by=tool.task_id,
                        )
                    )
                ]
                if tool.output is not None
                else None
            }
        )
        task.started_at = tool.started_at
        task.ended_at = tool.ended_at or tool.started_at
        task.utc_timestamp = task.started_at
        self._normalize_against_active_parent(task)
        self._normalize_child_task_bounds(task)
        task.status = _task_status(task.ended_at, tool.output)
        task.enrich(self.plugin_key)
        self._intercept_task(task)
        tool.emitted = True

    def _merge_tool_into_declared_evaluation(
        self,
        tool: ToolInvocationState,
        invocation: ModelInvocationState,
    ) -> bool:
        evaluation = self._active_tagged_task(PROV_AGENT_LOOP.EVALUATION.value)
        if evaluation is None:
            return False
        self._append_unique_message(evaluation.used_entities, _entity("tool", name=tool.tool_name))
        if tool.arguments is not None:
            self._append_unique_message(
                evaluation.used_entities,
                _entity(self._tool_data_entity_type(tool, tool.arguments), content=tool.arguments),
            )
        if tool.output is not None:
            self._append_unique_message(
                evaluation.generated_entities,
                _entity(
                    "evaluation_result",
                    content=tool.output,
                    attributed_to=invocation.agent_id,
                    generated_by=evaluation.task_id,
                ),
            )
        tool.emitted = True
        return True

    def _flush_open_records(self):
        for turn in self._turns.values():
            for invocation in turn.invocations:
                for tool in invocation.tools.values():
                    if not tool.emitted:
                        self._emit_tool(tool, invocation)
                if not invocation.emitted:
                    self._emit_invocation(invocation)
            if not turn.emitted:
                turn.ended_at = turn.ended_at or get_utc_now()
                self._discard_empty_started_tagged_tasks()
                self._emit_turn(turn)

    def _current_turn(self) -> TurnState | None:
        if self._current_turn_id:
            return self._turns.get(self._current_turn_id)
        return None

    def _active_workflow_id(self, fallback_workflow_id: str | None) -> str | None:
        return self._active_execution_plan_workflow_id or fallback_workflow_id

    def _workflow_for_turn(self, turn: TurnState) -> str | None:
        if turn.metadata.get("collaboration_mode_kind") == "plan":
            return turn.workflow_id
        if turn.metadata.get("produced_execution_plan_id"):
            return turn.workflow_id
        if turn.metadata.get("active_execution_plan_id"):
            return turn.metadata.get("active_execution_plan_id")
        return self._active_workflow_id(turn.workflow_id)

    def _should_emit_fallback_loop(self, turn: TurnState, workflow_id: str | None) -> bool:
        if turn.metadata.get("declared_loop_seen"):
            return False
        if turn.metadata.get("produced_execution_plan_id"):
            return False
        if workflow_id == self._session_id:
            return False
        return workflow_id is not None

    def _parent_for_observed_loop(self, turn: TurnState) -> str | None:
        return turn.metadata.get("active_plan_step_id")

    def _active_loop_context(self) -> TaggedTaskState | None:
        return self._active_tagged_task(PROV_AGENT_LOOP.LOOP_ITERATION.value)

    def _apply_active_context_to_invocation(self, invocation: ModelInvocationState):
        loop = self._active_loop_context()
        if not loop or invocation.emitted:
            return
        self._reparent_invocation_to_loop(invocation, loop)

    def _workflow_for_tagged_task(self, invocation: ModelInvocationState, subtype: str) -> str | None:
        if subtype == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value:
            return self._active_workflow_id(invocation.workflow_id)
        return self._active_workflow_id(invocation.workflow_id)

    def _parent_for_tagged_task(self, subtype: str) -> str | None:
        if subtype == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value:
            return None
        if subtype == PROV_AGENT_LOOP.LOOP_ITERATION.value:
            step = self._active_tagged_task(PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
            return step.task_id if step else None
        if subtype == PROV_AGENT_LOOP.EVALUATION.value:
            loop = self._active_tagged_task(PROV_AGENT_LOOP.LOOP_ITERATION.value)
            if loop:
                return loop.task_id
            step = self._active_tagged_task(PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
            return step.task_id if step else None
        return None

    def _parent_for_observed_task(
        self,
        subtype: str,
        workflow_id: str | None,
        fallback: str | None,
    ) -> str | None:
        if subtype == PROV_AGENT_LOOP.EVALUATION.value:
            declared_evaluation = self._active_tagged_task(PROV_AGENT_LOOP.EVALUATION.value)
            if declared_evaluation and declared_evaluation.workflow_id == workflow_id:
                return declared_evaluation.task_id
        loop = self._active_tagged_task(PROV_AGENT_LOOP.LOOP_ITERATION.value)
        if loop and loop.workflow_id == workflow_id:
            return loop.task_id
        turn = self._current_turn()
        if turn and workflow_id and turn.metadata.get("last_loop_iteration_workflow_id") == workflow_id:
            last_loop_id = turn.metadata.get("last_loop_iteration_id")
            if last_loop_id:
                return last_loop_id
        return fallback

    def _active_tagged_task(self, subtype: str) -> TaggedTaskState | None:
        for state in reversed(list(self._active_tagged_tasks.values())):
            if state.subtype == subtype:
                return state
        return None

    def _append_declared_entity_to_active_context(
        self,
        invocation: ModelInvocationState,
        entity: JsonObject,
        entity_type: str,
    ):
        evaluation = self._active_tagged_task(PROV_AGENT_LOOP.EVALUATION.value)
        if evaluation:
            if entity_type in {"mandate", "evaluation_criteria"}:
                self._append_unique_message(evaluation.used_entities, entity)
            else:
                self._append_unique_message(evaluation.generated_entities, entity)
            return
        if not invocation.emitted:
            if entity_type in {"mandate", "evaluation_criteria"}:
                self._append_unique_message(invocation.used_entities, entity)
            else:
                self._append_unique_message(invocation.generated_entities, entity)

    def _remember_tagged_context(self, invocation: ModelInvocationState, state: TaggedTaskState):
        turn = self._turns.get(invocation.turn_id)
        if not turn:
            return
        if state.workflow_id and state.workflow_id != self._session_id:
            turn.metadata["active_execution_plan_id"] = state.workflow_id
            invocation.workflow_id = state.workflow_id
        if state.subtype == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value:
            turn.metadata["active_plan_step_id"] = state.task_id
            turn.metadata["active_plan_step_label"] = state.metadata.get("label")

    def _start_observed_loop_context(
        self,
        invocation: ModelInvocationState,
        event: JsonObject,
        workflow_id: str | None,
        timestamp: float | None,
    ):
        turn = self._turns.get(invocation.turn_id)
        self._emit_stale_invocation_before_new_loop(invocation, turn)
        metadata = self._tagged_task_metadata(event, invocation)
        started_at = timestamp or invocation.started_at
        fallback_children_started_at = self._fallback_turn_children_started_at(turn)
        if fallback_children_started_at is not None:
            started_at = min(started_at or fallback_children_started_at, fallback_children_started_at - 0.001)
        active_step = self._active_tagged_task(PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
        if active_step and fallback_children_started_at is not None:
            active_step.started_at = min(
                active_step.started_at or fallback_children_started_at,
                fallback_children_started_at - 0.002,
            )
            if active_step.emitted_started:
                self._update_buffered_task_context(
                    active_step.task_id,
                    workflow_id=active_step.workflow_id,
                    parent_task_id=active_step.parent_task_id,
                    started_at=active_step.started_at,
                )
        active_step = self._active_tagged_task(PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value)
        if active_step and active_step.started_at is not None and started_at is not None:
            if started_at <= active_step.started_at:
                started_at = active_step.started_at + 0.001
            elif started_at == invocation.started_at:
                started_at -= 0.001
        state = TaggedTaskState(
            task_id=self._next_tagged_task_id(invocation, PROV_AGENT_LOOP.LOOP_ITERATION.value),
            subtype=PROV_AGENT_LOOP.LOOP_ITERATION.value,
            activity_id="loop_iteration",
            workflow_id=workflow_id,
            parent_task_id=self._parent_for_tagged_task(PROV_AGENT_LOOP.LOOP_ITERATION.value),
            agent_id=invocation.agent_id,
            source_agent_id=invocation.source_agent_id,
            started_at=started_at,
            used_messages=self._tagged_task_used_messages(
                event,
                invocation,
                PROV_AGENT_LOOP.LOOP_ITERATION.value,
                workflow_id,
            ),
            used_entities=self._tagged_task_used_entities(
                event,
                invocation,
                PROV_AGENT_LOOP.LOOP_ITERATION.value,
                workflow_id,
            ),
            metadata={**metadata, "observed_loop_iteration": True},
        )
        self._active_tagged_tasks[self._tagged_task_key(event)] = state
        if turn:
            self._adopt_fallback_turn_children_into_loop(turn, state)
        self._emit_tagged_task(state, timestamp, final=False)
        if turn:
            turn.metadata.update(
                _compact_dict(
                    {
                        "active_execution_plan_id": workflow_id if workflow_id != self._session_id else None,
                        "active_loop_iteration_id": state.task_id,
                        "declared_loop_label": event.get("label"),
                        "declared_loop_summary": event.get("summary") or event.get("content"),
                        "declared_loop_started_at": started_at,
                        "declared_loop_seen": True,
                    }
                )
            )
            for message in state.used_messages:
                self._append_unique_message(turn.messages, message)
        if workflow_id and workflow_id != self._session_id:
            invocation.workflow_id = workflow_id
        if not invocation.emitted:
            self._reparent_invocation_to_loop(invocation, state)
        if turn:
            for turn_invocation in turn.invocations:
                if turn_invocation is invocation:
                    continue
                if not turn_invocation.emitted and turn_invocation.ended_at is None:
                    self._reparent_invocation_to_loop(turn_invocation, state)

    def _reparent_invocation_to_loop(
        self,
        invocation: ModelInvocationState,
        state: TaggedTaskState,
    ):
        if invocation.emitted:
            return
        if state.workflow_id and state.workflow_id != self._session_id:
            invocation.workflow_id = state.workflow_id
        invocation.parent_task_id = state.task_id
        if invocation.started_at is not None and state.started_at is not None:
            invocation.started_at = max(invocation.started_at, state.started_at + 0.001)
        for tool in invocation.tools.values():
            if tool.emitted:
                continue
            tool.workflow_id = invocation.workflow_id
            tool.parent_task_id = state.task_id
        if invocation.emitted_started:
            self._emit_invocation_start_update(invocation)
        self._move_buffered_task_before_descendants(state.task_id)
        if state.parent_task_id:
            self._move_buffered_task_before_descendants(state.parent_task_id)

    def _fallback_turn_children_started_at(self, turn: TurnState | None) -> float | None:
        if not turn:
            return None
        started_at_values: list[float] = []
        for invocation in turn.invocations:
            if invocation.parent_task_id != turn.task_id:
                continue
            if invocation.started_at is not None:
                started_at_values.append(invocation.started_at)
            started_at_values.extend(
                tool.started_at
                for tool in invocation.tools.values()
                if tool.parent_task_id == turn.task_id and tool.started_at is not None
            )
        return min(started_at_values, default=None)

    def _adopt_fallback_turn_children_into_loop(
        self,
        turn: TurnState,
        state: TaggedTaskState,
    ):
        adopted = False
        for invocation in turn.invocations:
            if invocation.parent_task_id != turn.task_id:
                continue
            invocation.parent_task_id = state.task_id
            if state.workflow_id and state.workflow_id != self._session_id:
                invocation.workflow_id = state.workflow_id
            self._update_buffered_task_context(
                invocation.task_id,
                workflow_id=invocation.workflow_id,
                parent_task_id=state.task_id,
            )
            for tool in invocation.tools.values():
                if tool.parent_task_id != turn.task_id:
                    continue
                tool.parent_task_id = state.task_id
                tool.workflow_id = invocation.workflow_id
                self._update_buffered_task_context(
                    tool.task_id,
                    workflow_id=tool.workflow_id,
                    parent_task_id=state.task_id,
                )
            adopted = True
        if adopted:
            turn.emitted = True

    def _emit_invocation_start_update(self, invocation: ModelInvocationState):
        if invocation.emitted:
            return
        task = self._invocation_task(invocation, final=False)
        self._intercept_task(task)

    def _emit_stale_invocation_before_new_loop(
        self,
        invocation: ModelInvocationState,
        turn: TurnState | None,
    ):
        if not turn or invocation.emitted or invocation.ended_at is None:
            return
        active_loop_id = turn.metadata.get("active_loop_iteration_id")
        if active_loop_id and invocation.parent_task_id == active_loop_id:
            return
        if invocation.parent_task_id:
            self._emit_invocation(invocation)
            if turn.current_invocation is invocation:
                turn.current_invocation = None

    def _finish_observed_loop_context(
        self,
        invocation: ModelInvocationState,
        event: JsonObject,
        state: TaggedTaskState | None,
        timestamp: float | None,
    ):
        turn = self._turns.get(invocation.turn_id)
        if not turn:
            return
        if state is None:
            return
        state.generated_messages.extend(self._tagged_task_generated_messages(event, invocation, state.subtype))
        state.generated_entities.extend(self._tagged_task_generated_entities(event, invocation, state.subtype))
        state.metadata.update(self._tagged_task_metadata(event, invocation))
        self._emit_tagged_task(state, timestamp, final=True)
        turn.metadata.pop("active_loop_iteration_id", None)
        turn.metadata["last_loop_iteration_id"] = state.task_id
        turn.metadata["last_loop_iteration_workflow_id"] = state.workflow_id
        invocation_to_close = turn.current_invocation
        if invocation_to_close is None and invocation.parent_task_id == state.task_id:
            invocation_to_close = invocation
        if invocation_to_close and not invocation_to_close.emitted:
            invocation_to_close.ended_at = timestamp or invocation_to_close.ended_at
            self._emit_invocation(invocation_to_close)
            if turn.current_invocation is invocation_to_close:
                turn.current_invocation = None

    def _clear_finished_tagged_context(
        self,
        invocation: ModelInvocationState,
        state: TaggedTaskState,
        timestamp: float | None = None,
    ):
        turn = self._turns.get(invocation.turn_id)
        if not turn:
            return
        if state.subtype == PROV_AGENT_LOOP.LOOP_ITERATION.value:
            turn.metadata.pop("active_loop_iteration_id", None)
            turn.metadata["last_loop_iteration_id"] = state.task_id
            turn.metadata["last_loop_iteration_workflow_id"] = state.workflow_id
        elif state.subtype == PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value:
            if turn.metadata.get("active_plan_step_id") == state.task_id:
                turn.metadata.pop("active_plan_step_id", None)
                turn.metadata.pop("active_plan_step_label", None)
            self._mark_execution_plan_step_finished(state, timestamp)

    def _mark_execution_plan_step_finished(self, state: TaggedTaskState, timestamp: float | None):
        workflow_id = state.workflow_id
        if not workflow_id:
            return
        expected_steps = self._execution_plan_steps.get(workflow_id)
        if not expected_steps:
            return
        label = _canonical_plan_step_label(state.metadata.get("label") or state.activity_id)
        if not label or label not in expected_steps:
            return
        finished_steps = self._execution_plan_finished_steps.setdefault(workflow_id, set())
        finished_steps.add(label)
        if expected_steps.issubset(finished_steps):
            self._finish_execution_plan_workflow(workflow_id, state, timestamp)
            if self._active_execution_plan_workflow_id == workflow_id:
                self._active_execution_plan_workflow_id = None
            if self._pending_execution_plan_workflow_id == workflow_id:
                self._pending_execution_plan_workflow_id = None
                self._pending_execution_plan_turn_id = None

    def _finish_execution_plan_workflow(
        self,
        workflow_id: str,
        state: TaggedTaskState,
        timestamp: float | None,
    ):
        workflow = WorkflowObject(workflow_id=workflow_id, name="execution_plan")
        workflow.subtype = PROV_AGENT_LOOP.EXECUTION_PLAN.value
        workflow.campaign_id = self._campaign_id()
        workflow.agent_id = state.agent_id
        workflow.ended_at = timestamp or state.started_at
        workflow.status = Status.FINISHED
        self._send_workflow_message(workflow)

    def _loop_iteration_status(self, ended_at: float | None, metadata: JsonObject) -> Status:
        declared_status = metadata.get("declared_loop_status")
        if declared_status in {"finished", "passed"}:
            return Status.FINISHED
        if declared_status in {"failed", "error"}:
            return Status.ERROR
        return _task_status(ended_at, metadata)

    def _tagged_task_kind(self, event_type: str) -> tuple[str, str]:
        if event_type.startswith("plan_step_"):
            return PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value, "plan_step_execution"
        if event_type.startswith("loop_iteration_"):
            return PROV_AGENT_LOOP.LOOP_ITERATION.value, "loop_iteration"
        if event_type.startswith("evaluation_"):
            return PROV_AGENT_LOOP.EVALUATION.value, "evaluation"
        return event_type, event_type

    def _tagged_task_key(self, event: JsonObject) -> tuple[str, str]:
        event_type = event.get("type")
        identity = (
            event.get("evaluation_id")
            or event.get("loop_id")
            or event.get("step_id")
            or event.get("step")
            or event.get("label")
            or event.get("command")
            or event_type
        )
        return event_type, str(identity)

    def _next_tagged_task_id(self, invocation: ModelInvocationState, subtype: str) -> str:
        count = self._tagged_task_counts.get(subtype, 0) + 1
        self._tagged_task_counts[subtype] = count
        return f"{invocation.turn_id}:{subtype}:{count}"

    def _tagged_task_metadata(self, event: JsonObject, invocation: ModelInvocationState) -> JsonObject:
        return _compact_dict(
            {
                key: value
                for key, value in event.items()
                if key not in {"content", "summary", "result", "criteria", "criteria_ids"}
            }
            | {
                "turn_id": invocation.turn_id,
                "ai_model_invocation_id": invocation.task_id,
            }
        )

    def _tagged_task_used_messages(
        self,
        event: JsonObject,
        invocation: ModelInvocationState,
        subtype: str,
        workflow_id: str | None,
    ) -> list[JsonObject]:
        return []

    def _tagged_task_used_entities(
        self,
        event: JsonObject,
        invocation: ModelInvocationState,
        subtype: str,
        workflow_id: str | None,
    ) -> list[JsonObject]:
        entities = []
        if subtype == PROV_AGENT_LOOP.EVALUATION.value:
            entities.extend(self._criteria_entities_from_event(event, workflow_id, invocation.agent_id))
        return entities

    def _tagged_task_generated_messages(
        self,
        event: JsonObject,
        invocation: ModelInvocationState,
        subtype: str,
    ) -> list[JsonObject]:
        if subtype in {
            PROV_AGENT_LOOP.EVALUATION.value,
            PROV_AGENT_LOOP.PLAN_STEP_EXECUTION.value,
            PROV_AGENT_LOOP.LOOP_ITERATION.value,
        }:
            return []
        content = event.get("summary") or event.get("result") or event.get("content")
        message_type = "message"
        return (
            [
                _entity(
                    message_type,
                    content=content,
                    attributed_to=invocation.agent_id,
                    status=event.get("status"),
                )
            ]
            if content
            else []
        )

    def _tagged_task_generated_entities(
        self,
        event: JsonObject,
        invocation: ModelInvocationState,
        subtype: str,
    ) -> list[JsonObject]:
        content = event.get("result") or event.get("summary") or event.get("content")
        if subtype == PROV_AGENT_LOOP.EVALUATION.value:
            return (
                [
                    _entity(
                        "evaluation_result",
                        content=content,
                        status=event.get("status"),
                        decision=event.get("decision"),
                        reason=event.get("reason"),
                        attributed_to=invocation.agent_id,
                    )
                ]
                if content or event.get("status")
                else []
            )
        return []

    def _criteria_entities_from_event(
        self,
        event: JsonObject,
        workflow_id: str | None,
        attributed_to: str | None,
    ) -> list[JsonObject]:
        entities = []
        for index, criterion in enumerate(event.get("criteria") or [], start=1):
            entities.append(_entity("evaluation_criteria", content=criterion, attributed_to=attributed_to, index=index))
        for criterion_id in event.get("criteria_ids") or []:
            entities.append(_entity("evaluation_criteria", criteria_id=criterion_id, attributed_to=attributed_to))
        if not entities and workflow_id and event.get("criteria_match") == "all_active_plan_criteria":
            entities.extend(self._execution_plan_criteria.get(workflow_id, []))
        return entities

    def _event_attributed_to(self, event: JsonObject, invocation: ModelInvocationState) -> str | None:
        attributed_to = event.get("attributed_to")
        if attributed_to == "human":
            return invocation.source_agent_id
        if attributed_to in {"agent", "codex", "assistant"}:
            return invocation.agent_id
        return attributed_to or invocation.agent_id

    def _agent_response_from_events(self, text: str | None) -> str | None:
        for event in reversed(_extract_flowcept_events(text)):
            if event.get("type") == "agent_response" and event.get("content"):
                return event["content"]
        return None

    def _activate_pending_execution_plan(self, turn_id: str | None):
        if turn_id is None or self._pending_execution_plan_turn_id != turn_id:
            return
        self._active_execution_plan_workflow_id = self._pending_execution_plan_workflow_id
        self._pending_execution_plan_workflow_id = None
        self._pending_execution_plan_turn_id = None

    def _is_test_command(self, arguments: Any) -> bool:
        if isinstance(arguments, dict):
            command = arguments.get("cmd") or arguments.get("command")
        else:
            command = arguments
        if not isinstance(command, str):
            return False
        stripped = command.strip()
        first_line = stripped.splitlines()[0].strip() if stripped else ""
        if re.match(r"^(cat|tee|printf|echo|sed|awk|perl|apply_patch)\b", first_line):
            return False
        return bool(
            re.search(
                r"(^|[;&|]\s*)("
                r"test|pytest|unittest|ruff|mypy|pyright|eslint|vitest|jest|"
                r"cargo\s+test|npm\s+test|pnpm\s+test|yarn\s+test|go\s+test|"
                r"python(?:3(?:\.\d+)?)?\s+-m\s+(?:pytest|unittest|py_compile)|"
                r"uv\s+run(?:\s+--with\s+\S+)*\s+(?:pytest|python(?:3(?:\.\d+)?)?\s+-m\s+pytest)"
                r")(\s|$)",
                first_line,
            )
        )

    def _tool_used_messages(
        self,
        tool: ToolInvocationState,
        invocation: ModelInvocationState,
        workflow_id: str | None,
        is_evaluation: bool,
    ) -> list[JsonObject]:
        return []

    def _tool_used_entities(
        self,
        tool: ToolInvocationState,
        workflow_id: str | None,
        is_evaluation: bool,
    ) -> list[JsonObject]:
        entities = []
        entities.append(_entity("tool", name=tool.tool_name))
        if tool.arguments is not None:
            entities.append(_entity(self._tool_data_entity_type(tool, tool.arguments), content=tool.arguments))
        if is_evaluation and workflow_id:
            entities.extend(self._execution_plan_criteria.get(workflow_id, []))
        return entities

    def _tool_data_entity_type(self, tool: ToolInvocationState, value: Any) -> str:
        text_parts = [str(tool.tool_name or "")]
        if isinstance(tool.arguments, dict):
            text_parts.extend(str(item) for pair in tool.arguments.items() for item in pair)
        elif tool.arguments is not None:
            text_parts.append(str(tool.arguments))
        if value is not None and value is not tool.arguments:
            text_parts.append(str(value))
        haystack = "\n".join(text_parts)
        if TOOL_DATA_TELEMETRY_PATTERNS.search(haystack):
            return "telemetry_data"
        if TOOL_DATA_SCHEDULING_PATTERNS.search(haystack):
            return "scheduling_data"
        if tool.tool_name:
            return "domain_data"
        return "entity"

    def _evaluation_criteria_match(self, workflow_id: str | None) -> str:
        if workflow_id and self._execution_plan_criteria.get(workflow_id):
            return "all_active_plan_criteria"
        return "unresolved"

    def _find_invocation_for_call(self, call_id: str | None) -> ModelInvocationState | None:
        if not call_id:
            return None
        for turn in self._turns.values():
            for invocation in turn.invocations:
                if call_id in invocation.tools:
                    return invocation
        return None

    def _workflow_provider(self) -> str | None:
        return self._model_provider

    def _prompt_from_messages(self, messages: list[JsonObject]) -> str | None:
        for message in reversed(messages):
            if (message.get("role") == "user" or message.get("type") == "user_prompt") and message.get("content"):
                return message["content"]
        return None

    def _append_unique_message(self, messages: list[JsonObject], message: JsonObject):
        for existing in messages:
            if (
                existing.get("type") == message.get("type")
                and existing.get("role") == message.get("role")
                and existing.get("content") == message.get("content")
            ):
                return
        messages.append(message)

    def _normalize_child_task_bounds(self, task: TaskObject):
        if not hasattr(self, "_emitted_task_bounds"):
            self._emitted_task_bounds = {}
        if not task.parent_task_id:
            return
        parent_bounds = self._emitted_task_bounds.get(task.parent_task_id)
        if not parent_bounds:
            return
        parent_started_at, parent_ended_at = parent_bounds
        if parent_started_at is not None:
            if task.started_at is None or task.started_at < parent_started_at:
                task.started_at = parent_started_at
        if parent_ended_at is not None:
            if task.ended_at is None or task.ended_at > parent_ended_at:
                task.ended_at = parent_ended_at
            if task.started_at is None or task.started_at > parent_ended_at:
                task.started_at = parent_ended_at
        if task.started_at is not None and task.ended_at is not None and task.ended_at < task.started_at:
            task.ended_at = task.started_at
        task.utc_timestamp = task.started_at

    def _normalize_against_active_parent(self, task: TaskObject):
        if not task.parent_task_id:
            return
        parent = next(
            (state for state in self._active_tagged_tasks.values() if state.task_id == task.parent_task_id),
            None,
        )
        if parent is None or parent.started_at is None:
            return
        if task.started_at is None or task.started_at < parent.started_at:
            task.started_at = parent.started_at
        if task.ended_at is not None and task.ended_at < task.started_at:
            task.ended_at = task.started_at
        task.utc_timestamp = task.started_at

    def _intercept_task(self, task: TaskObject):
        if not hasattr(self, "_emitted_task_bounds"):
            self._emitted_task_bounds = {}
        if task.campaign_id is None:
            task.campaign_id = self._campaign_id()
        self._emitted_task_bounds[task.task_id] = (task.started_at, task.ended_at)
        task_msg = task.to_dict()
        if self._replace_buffered_task(task_msg):
            return
        self.intercept(task_msg)

    def _send_workflow_message(self, workflow: WorkflowObject):
        workflow.enrich(self.plugin_key)
        workflow_msg = workflow.to_dict()
        if self._replace_buffered_workflow(workflow_msg):
            return
        self.send_workflow_message(workflow)

    def _replace_buffered_workflow(self, workflow_msg: JsonObject) -> bool:
        workflow_id = workflow_msg.get("workflow_id")
        if not workflow_id:
            return False
        buffer = self._current_task_buffer()
        if buffer is None:
            return False
        for index, existing in enumerate(buffer):
            if existing.get("type") != "workflow" or existing.get("workflow_id") != workflow_id:
                continue
            updated = dict(existing)
            for key, value in workflow_msg.items():
                if isinstance(value, dict) and isinstance(updated.get(key), dict):
                    updated[key] = {**updated[key], **value}
                else:
                    updated[key] = value
            buffer[index] = updated
            return True
        return False

    def _replace_buffered_task(self, task_msg: JsonObject) -> bool:
        task_id = task_msg.get("task_id")
        if not task_id:
            return False
        buffer = self._current_task_buffer()
        if buffer is None:
            return False
        for index, existing in enumerate(buffer):
            if existing.get("task_id") == task_id:
                updated = dict(existing)
                for key, value in task_msg.items():
                    if isinstance(value, dict) and isinstance(updated.get(key), dict):
                        updated[key] = {**updated[key], **value}
                    else:
                        updated[key] = value
                buffer[index] = updated
                return True
        return False

    def _update_buffered_task_context(
        self,
        task_id: str,
        *,
        workflow_id: str | None,
        parent_task_id: str | None,
        started_at: float | None = None,
    ):
        buffer = self._current_task_buffer()
        if buffer is None:
            return
        for record in buffer:
            if record.get("task_id") != task_id:
                continue
            record["workflow_id"] = workflow_id
            record["parent_task_id"] = parent_task_id
            if started_at is not None:
                record["started_at"] = started_at
                record["utc_timestamp"] = started_at
            current_bounds = self._emitted_task_bounds.get(task_id, (None, None))
            self._emitted_task_bounds[task_id] = (
                started_at if started_at is not None else current_bounds[0],
                current_bounds[1],
            )
            return

    def _current_task_buffer(self) -> list[JsonObject] | None:
        mq_dao = getattr(self, "_mq_dao", None)
        if mq_dao is None:
            return None
        buffer = getattr(mq_dao, "buffer", None)
        if hasattr(buffer, "current_buffer"):
            buffer = buffer.current_buffer
        return buffer if isinstance(buffer, list) else None

    def _move_buffered_task_before_descendants(self, task_id: str):
        buffer = self._current_task_buffer()
        if buffer is None:
            return
        parent_index = next(
            (index for index, record in enumerate(buffer) if record.get("task_id") == task_id),
            None,
        )
        if parent_index is None:
            return
        descendant_index = next(
            (
                index
                for index, record in enumerate(buffer)
                if record.get("parent_task_id") == task_id and index < parent_index
            ),
            None,
        )
        if descendant_index is None:
            return
        record = buffer.pop(parent_index)
        buffer.insert(descendant_index, record)

    def _discard_empty_started_tagged_tasks(self):
        buffer = self._current_task_buffer()
        if buffer is None:
            return
        changed = True
        while changed:
            changed = False
            for key, state in list(self._active_tagged_tasks.items()):
                if not state.emitted_started:
                    continue
                if self._buffered_task_has_child(state.task_id):
                    continue
                if self._remove_buffered_task(state.task_id):
                    self._active_tagged_tasks.pop(key, None)
                    self._emitted_task_bounds.pop(state.task_id, None)
                    changed = True

    def _buffered_task_has_child(self, task_id: str) -> bool:
        buffer = self._current_task_buffer()
        if buffer is None:
            return False
        return any(record.get("parent_task_id") == task_id for record in buffer)

    def _remove_buffered_task(self, task_id: str) -> bool:
        buffer = self._current_task_buffer()
        if buffer is None:
            return False
        for index, record in enumerate(buffer):
            if record.get("task_id") == task_id:
                buffer.pop(index)
                return True
        return False

    def _agent_obj(self, agent_id: str, name: str) -> AgentObject:
        agent = AgentObject(agent_id=agent_id, name=name, workflow_id=self._session_id, campaign_id=self._campaign_id())
        agent.extra_metadata = {"source": "codex_jsonl"}
        agent.enrich()
        return agent

    def _campaign_id(self) -> str | None:
        try:
            from flowcept.flowcept_api.flowcept_controller import Flowcept

            return Flowcept.campaign_id
        except Exception:
            return None
