"""The state machine that turns harness events into PROV-AGENT records.

This is the only place that knows how a coding session decomposes into
provenance:

    session          -> workflow (subtype ``agent_session``)
      turn           -> task (subtype ``ai_model_invocation``, granularity=turn)
        tool call    -> task (subtype ``agent_tool``, parent = the turn)
        subagent     -> nested workflow + task
      lifecycle      -> task (subtype ``harness_event``)

The parent/child edges are what make the capture useful: given a bad file
edit you can walk up to the turn that caused it and the prompt that started
it, which is the ``wasInformedBy`` chain PROV-AGENT is built around.
"""

from __future__ import annotations

import time
from typing import Any

from . import ids, prov, vocab
from .config import Config, load_config
from .emit import Emitter
from .events import HarnessEvent
from .sanitize import Sanitizer
from .state import session_state
from .vocab import EventKind


class Recorder:
    """Applies one :class:`HarnessEvent` to a session's provenance."""

    def __init__(self, config: Config | None = None, on_error=None):
        self.config = config or load_config()
        self.sanitizer = Sanitizer(self.config)
        self._on_error = on_error
        self._supersede: set[str] = set()

    # -- public API ----------------------------------------------------------

    def record(self, event: HarnessEvent) -> list[dict[str, Any]]:
        """Process an event; return the records that were emitted."""
        if not self.config.enabled:
            return []

        workflow_id = ids.workflow_id_for(event.harness, event.session_id)
        emitter = Emitter(self.config, workflow_id, on_error=self._on_error)

        # Workflow ids whose "open" record this event's records replace; see
        # JsonlEmitter.write.
        self._supersede: set[str] = set()

        with session_state(self.config.state_path(workflow_id)) as state:
            records = self._dispatch(event, workflow_id, state)

        if records:
            emitter.emit(*records, supersede=frozenset(self._supersede) or None)
        return records

    # -- dispatch ------------------------------------------------------------

    def _dispatch(self, event: HarnessEvent, workflow_id: str, state) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []

        # Every event can be the first one we see: a hook may be installed
        # mid-session, or SessionStart may not exist on this harness.
        records.extend(self._ensure_session(event, workflow_id, state))

        handler = {
            EventKind.SESSION_START: self._noop,
            EventKind.PROMPT: self._on_prompt,
            EventKind.TURN_END: self._on_turn_end,
            EventKind.TOOL_PRE: self._on_tool_pre,
            EventKind.TOOL_POST: self._on_tool_post,
            EventKind.TOOL_ERROR: self._on_tool_post,
            EventKind.LLM_CALL: self._on_llm_call,
            EventKind.SUBAGENT_START: self._on_subagent_start,
            EventKind.SUBAGENT_STOP: self._on_subagent_stop,
            EventKind.NOTIFICATION: self._on_lifecycle_event,
            EventKind.COMPACT: self._on_lifecycle_event,
            EventKind.SESSION_END: self._on_session_end,
        }.get(event.kind)

        if handler is None:
            self._warn(f"unknown event kind {event.kind!r}")
            return records

        records.extend(handler(event, workflow_id, state))
        return records

    # -- session -------------------------------------------------------------

    def _ensure_session(self, event: HarnessEvent, workflow_id: str, state) -> list[dict[str, Any]]:
        campaign_id = self._campaign_id(event, state)
        agent_id = ids.agent_id_for(event.harness, event.session_id)

        # Late-arriving context (the model is only on SessionStart) is folded in
        # as it becomes known.
        for key, value in (
            ("harness", event.harness),
            ("session_id", event.session_id),
            ("workflow_id", workflow_id),
            ("campaign_id", campaign_id),
            ("agent_id", agent_id),
            # Only the harness's own cwd, never the fallback derived from the
            # hook process, which may run from somewhere else entirely.
            ("cwd", event.cwd),
            ("project_dir", event.project_dir),
            ("model", event.model),
        ):
            if value is not None:
                state.set(key, value)
        state.setdefault("started_at", event.timestamp)
        state.setdefault("counters", {})
        if event.kind == EventKind.SESSION_START and event.source:
            state.setdefault("start_reason", event.source)

        if not state.mark_once("session_opened"):
            return []

        name = f"{event.harness} session"
        used = self._clean_dict(
            {
                "cwd": event.cwd,
                "project_dir": event.project_dir,
                "model": event.model,
                "session_id": event.session_id,
                "start_reason": state.get("start_reason"),
            }
        )
        return [
            prov.agent_record(
                agent_id=agent_id,
                name=f"{event.harness}:{event.model or 'assistant'}",
                workflow_id=workflow_id,
                campaign_id=campaign_id,
                extra_metadata={"harness": event.harness, "session_id": event.session_id},
            ),
            prov.workflow_record(
                workflow_id=workflow_id,
                campaign_id=campaign_id,
                name=name,
                subtype=vocab.AGENT_SESSION,
                agent_id=agent_id,
                used=used,
                custom_metadata={"harness": event.harness, "capture": "flowcept-harness"},
                started_at=event.timestamp,
                status=vocab.STATUS_RUNNING,
                description=f"Interactive {event.harness} session captured by flowcept-harness.",
            ),
        ]

    def _on_session_end(self, event: HarnessEvent, workflow_id: str, state) -> list[dict[str, Any]]:
        records = self._close_open_turn(event, workflow_id, state, reason="session_ended")
        counters = state.get("counters", {})
        # This record replaces the one written at session start, so it has to
        # carry that record's fields too.
        self._supersede.add(workflow_id)
        records.append(
            prov.workflow_record(
                workflow_id=workflow_id,
                campaign_id=state.get("campaign_id"),
                name=f"{event.harness} session",
                subtype=vocab.AGENT_SESSION,
                agent_id=state.get("agent_id"),
                used=self._clean_dict(
                    {
                        "cwd": state.get("cwd"),
                        "project_dir": state.get("project_dir"),
                        "model": state.get("model"),
                        "session_id": event.session_id,
                        "start_reason": state.get("start_reason"),
                    }
                ),
                generated=self._clean_dict(
                    {
                        "turns": counters.get("turns"),
                        "tool_calls": counters.get("tools"),
                        "tool_errors": counters.get("tool_errors"),
                        "subagents": counters.get("subagents"),
                    }
                ),
                custom_metadata={"harness": event.harness, "end_reason": event.source},
                started_at=state.get("started_at"),
                ended_at=event.timestamp,
                status=vocab.STATUS_FINISHED,
            )
        )
        state.set("ended_at", event.timestamp)
        return records

    # -- turns ---------------------------------------------------------------

    def _on_prompt(self, event: HarnessEvent, workflow_id: str, state):
        # A prompt while a turn is open means the previous turn never closed.
        records = self._close_open_turn(event, workflow_id, state, reason="superseded")

        turn_number = int(state.get("counters", {}).get("turns", 0)) + 1
        turn_key = event.prompt_id or f"n{turn_number}"
        task_id = ids.turn_task_id(workflow_id, turn_key)

        state.set(
            "current_turn",
            {
                "task_id": task_id,
                "turn_key": turn_key,
                "number": turn_number,
                "started_at": event.timestamp,
                "prompt": self._prompt_value(event.prompt),
                "tool_task_ids": [],
                "permission_mode": event.permission_mode,
                "effort": event.effort,
            },
        )
        self._bump(state, "turns")
        return records

    def _on_turn_end(self, event: HarnessEvent, workflow_id: str, state):
        turn = state.get("current_turn")
        if not turn:
            # Stop without a matching prompt (hook installed mid-turn). Record
            # the response alone rather than dropping it.
            turn = {
                "task_id": ids.turn_task_id(workflow_id, f"orphan-{int(event.timestamp * 1000)}"),
                "number": None,
                "started_at": event.timestamp,
                "prompt": None,
                "tool_task_ids": [],
            }
        state.set("current_turn", None)
        status = vocab.STATUS_ERROR if event.error else vocab.STATUS_FINISHED
        return [self._turn_task(event, workflow_id, state, turn, event.response, status)]

    def _close_open_turn(self, event: HarnessEvent, workflow_id: str, state, *, reason: str):
        turn = state.get("current_turn")
        if not turn:
            return []
        state.set("current_turn", None)
        return [
            self._turn_task(
                event,
                workflow_id,
                state,
                turn,
                None,
                vocab.STATUS_UNKNOWN,
                # The turn is closed, just not by a turn-end event: the user
                # interrupted, or the session went away underneath it.
                extra_metadata={"close_reason": reason},
            )
        ]

    def _turn_task(self, event, workflow_id, state, turn, response, status, extra_metadata=None):
        metadata = {
            "granularity": "turn",
            "harness": event.harness,
            "turn_number": turn.get("number"),
            "model": state.get("model"),
            "permission_mode": turn.get("permission_mode"),
            "effort": turn.get("effort"),
            "tool_task_ids": turn.get("tool_task_ids") or None,
            "tool_call_count": len(turn.get("tool_task_ids") or []),
        }
        if extra_metadata:
            metadata.update(extra_metadata)
        if event.usage:
            metadata["llm_usage"] = self.sanitizer.mapping(event.usage)

        generated = None
        if response is not None:
            generated = {"response": self._prompt_value(response)}

        return prov.task_record(
            task_id=turn["task_id"],
            workflow_id=workflow_id,
            campaign_id=state.get("campaign_id"),
            activity_id="agent_turn",
            subtype=vocab.AI_MODEL_INVOCATION,
            agent_id=state.get("agent_id"),
            source_agent_id=self._source_agent_id(event),
            used=self._clean_dict({"prompt": turn.get("prompt")}),
            generated=generated,
            custom_metadata=self._clean_dict(metadata),
            status=status,
            started_at=turn.get("started_at"),
            ended_at=event.timestamp,
            stderr=event.error,
        )

    # -- tools ---------------------------------------------------------------

    def _tool_key(self, event: HarnessEvent) -> str:
        return event.tool_use_id or f"{event.tool_name}@{event.timestamp}"

    def _on_tool_pre(self, event: HarnessEvent, workflow_id: str, state):
        turn = state.get("current_turn") or {}
        state.add_pending(
            self._tool_key(event),
            {
                "started_at": event.timestamp,
                "tool_name": event.tool_name,
                "used": self.sanitizer.mapping(event.tool_input) if event.tool_input is not None else None,
                "parent_task_id": turn.get("task_id"),
                "agent_ref": event.agent_ref,
            },
        )
        return []

    def _on_tool_post(self, event: HarnessEvent, workflow_id: str, state):
        key = self._tool_key(event)
        pending = state.pop_pending(key) or {}
        task_id = ids.tool_task_id(workflow_id, key)

        turn = state.get("current_turn") or {}
        parent_task_id = pending.get("parent_task_id") or turn.get("task_id")
        tool_name = event.tool_name or pending.get("tool_name") or "unknown_tool"

        used = pending.get("used")
        if used is None and event.tool_input is not None:
            used = self.sanitizer.mapping(event.tool_input)

        generated = None
        if self.config.capture_tool_results and event.tool_response is not None:
            generated = self.sanitizer.mapping(event.tool_response)

        is_error = event.kind == EventKind.TOOL_ERROR or bool(event.error)
        status = vocab.STATUS_ERROR if is_error else vocab.STATUS_FINISHED

        # Record the tool on its turn so the turn can list what it caused.
        if turn and turn.get("task_id") == parent_task_id:
            turn.setdefault("tool_task_ids", []).append(task_id)
            state.set("current_turn", turn)

        self._bump(state, "tools")
        if is_error:
            self._bump(state, "tool_errors")

        # A subagent's tool call belongs to the subagent's workflow, not the
        # session's, so the two do not interleave in dataflow views.
        target_workflow_id = workflow_id
        agent_id = state.get("agent_id")
        if event.agent_ref:
            sub = (state.get("subagents") or {}).get(event.agent_ref)
            if sub:
                target_workflow_id = sub.get("workflow_id", workflow_id)
                agent_id = sub.get("agent_id", agent_id)
                parent_task_id = sub.get("task_id") or parent_task_id

        return [
            prov.task_record(
                task_id=task_id,
                workflow_id=target_workflow_id,
                campaign_id=state.get("campaign_id"),
                activity_id=tool_name,
                subtype=vocab.AGENT_TOOL,
                agent_id=agent_id,
                source_agent_id=self._source_agent_id(event),
                parent_task_id=parent_task_id,
                used=used,
                generated=generated,
                custom_metadata=self._clean_dict(
                    {
                        "harness": event.harness,
                        "tool_name": tool_name,
                        "tool_use_id": event.tool_use_id,
                        "permission_mode": event.permission_mode,
                        "mcp_tool": bool(tool_name.startswith("mcp__")),
                        "duration_known": "started_at" in pending,
                    }
                ),
                status=status,
                # An event that reports its own duration (an OTel span) wins
                # over the start recorded by a matching pre-event, which wins
                # over "we only ever saw the end".
                started_at=event.started_at or pending.get("started_at", event.timestamp),
                ended_at=event.timestamp,
                stderr=event.error,
                tags=event.tags,
            )
        ]

    # -- model invocations ---------------------------------------------------

    def _on_llm_call(self, event: HarnessEvent, workflow_id: str, state):
        turn = state.get("current_turn") or {}
        call_key = event.call_id or f"{event.timestamp}"
        usage = self.sanitizer.mapping(event.usage) if event.usage else None
        metadata = self._clean_dict(
            {
                "granularity": "call",
                "harness": event.harness,
                "model": event.model or state.get("model"),
                "llm_usage": usage,
                "provider_request_id": event.call_id,
            }
        )
        self._bump(state, "llm_calls")
        return [
            prov.task_record(
                task_id=ids.llm_task_id(workflow_id, call_key),
                workflow_id=workflow_id,
                campaign_id=state.get("campaign_id"),
                activity_id="llm_interaction",
                subtype=vocab.AI_MODEL_INVOCATION,
                agent_id=state.get("agent_id"),
                source_agent_id=self._source_agent_id(event),
                parent_task_id=turn.get("task_id"),
                used=self._clean_dict({"prompt": self._prompt_value(event.prompt)}),
                generated=self._clean_dict({"response": self._prompt_value(event.response)}),
                custom_metadata=metadata,
                status=vocab.STATUS_ERROR if event.error else vocab.STATUS_FINISHED,
                started_at=event.started_at or event.timestamp,
                ended_at=event.timestamp,
                stderr=event.error,
            )
        ]

    # -- subagents -----------------------------------------------------------

    def _on_subagent_start(self, event: HarnessEvent, workflow_id: str, state):
        ref = event.agent_ref or event.agent_name or f"sub-{event.timestamp}"
        sub_workflow_id = ids.subagent_workflow_id(workflow_id, ref)
        sub_agent_id = ids.agent_id_for(event.harness, event.session_id, event.agent_name or ref)
        turn = state.get("current_turn") or {}

        subagents = state.get("subagents") or {}
        subagents[ref] = {
            "workflow_id": sub_workflow_id,
            "agent_id": sub_agent_id,
            "agent_name": event.agent_name,
            "started_at": event.timestamp,
            "task_id": turn.get("task_id"),
            # Kept so the closing record can restate what the open one said.
            "prompt": self._prompt_value(event.prompt),
        }
        state.set("subagents", subagents)
        self._bump(state, "subagents")

        return [
            prov.agent_record(
                agent_id=sub_agent_id,
                name=f"{event.harness}:{event.agent_name or 'subagent'}",
                workflow_id=sub_workflow_id,
                campaign_id=state.get("campaign_id"),
                extra_metadata={"harness": event.harness, "subagent_of": state.get("agent_id")},
            ),
            prov.workflow_record(
                workflow_id=sub_workflow_id,
                parent_workflow_id=workflow_id,
                campaign_id=state.get("campaign_id"),
                name=f"subagent:{event.agent_name or ref}",
                subtype=vocab.SUBAGENT_SESSION,
                agent_id=sub_agent_id,
                used=self._clean_dict({"agent_type": event.agent_name, "prompt": self._prompt_value(event.prompt)}),
                custom_metadata=self._clean_dict({"harness": event.harness, "spawned_by_task_id": turn.get("task_id")}),
                started_at=event.timestamp,
                status=vocab.STATUS_RUNNING,
            ),
        ]

    def _on_subagent_stop(self, event: HarnessEvent, workflow_id: str, state):
        ref = event.agent_ref or event.agent_name or ""
        subagents = state.get("subagents") or {}
        sub = subagents.pop(ref, None)
        state.set("subagents", subagents)

        if sub is None:
            sub = {
                "workflow_id": ids.subagent_workflow_id(workflow_id, ref or f"sub-{event.timestamp}"),
                "agent_id": ids.agent_id_for(event.harness, event.session_id, event.agent_name or ref),
                "started_at": event.timestamp,
            }

        agent_name = event.agent_name or sub.get("agent_name")
        self._supersede.add(sub["workflow_id"])
        return [
            prov.workflow_record(
                workflow_id=sub["workflow_id"],
                parent_workflow_id=workflow_id,
                campaign_id=state.get("campaign_id"),
                name=f"subagent:{agent_name or ref}",
                subtype=vocab.SUBAGENT_SESSION,
                agent_id=sub.get("agent_id"),
                used=self._clean_dict({"agent_type": agent_name, "prompt": sub.get("prompt")}),
                generated=self._clean_dict({"response": self._prompt_value(event.response)}),
                custom_metadata=self._clean_dict(
                    {
                        "harness": event.harness,
                        "agent_type": agent_name,
                        "spawned_by_task_id": sub.get("task_id"),
                    }
                ),
                started_at=sub.get("started_at"),
                ended_at=event.timestamp,
                status=vocab.STATUS_ERROR if event.error else vocab.STATUS_FINISHED,
            )
        ]

    # -- lifecycle -----------------------------------------------------------

    def _on_lifecycle_event(self, event: HarnessEvent, workflow_id: str, state):
        turn = state.get("current_turn") or {}
        key = f"{event.kind}-{event.timestamp}"
        return [
            prov.task_record(
                task_id=ids.event_task_id(workflow_id, event.kind, key),
                workflow_id=workflow_id,
                campaign_id=state.get("campaign_id"),
                activity_id=event.kind,
                subtype=vocab.HARNESS_EVENT,
                agent_id=state.get("agent_id"),
                parent_task_id=turn.get("task_id"),
                used=self._clean_dict({"trigger": event.source, "message": event.message}),
                custom_metadata=self._clean_dict({"harness": event.harness, "raw_event": self._raw(event)}),
                status=vocab.STATUS_FINISHED,
                started_at=event.timestamp,
                ended_at=event.timestamp,
            )
        ]

    def _noop(self, event, workflow_id, state):
        return []

    # -- helpers -------------------------------------------------------------

    def _campaign_id(self, event: HarnessEvent, state) -> str | None:
        existing = state.get("campaign_id")
        if existing:
            return existing
        if self.config.campaign_id:
            return self.config.campaign_id
        scope = self.config.campaign_scope
        if scope == "none":
            return None
        if scope == "global":
            return ids.campaign_id_for_project(None)
        return ids.campaign_id_for_project(event.project_dir or event.cwd)

    def _source_agent_id(self, event: HarnessEvent) -> str | None:
        """Cross-system source id for this event's task records.

        The ``flowcept_source_agent_id`` payload key (carried on the event)
        wins over the ``FLOWCEPT_HARNESS_SOURCE_AGENT_ID`` environment value
        (carried on the config). Only turn, tool, and LLM-call tasks get it:
        lifecycle events have no dataflow of their own, and session/subagent
        workflow records do not model the field.
        """
        return event.source_agent_id or self.config.source_agent_id

    def _prompt_value(self, text: str | None):
        if text is None:
            return None
        if not self.config.capture_prompts:
            return {"_summary": True, "chars": len(text), "sha256_16": ids.content_digest(text)}
        return self.sanitizer.value(text)

    def _raw(self, event: HarnessEvent):
        if not event.raw:
            return None
        return self.sanitizer.value(event.raw)

    @staticmethod
    def _clean_dict(data: dict[str, Any]) -> dict[str, Any] | None:
        cleaned = {k: v for k, v in data.items() if v is not None}
        return cleaned or None

    @staticmethod
    def _bump(state, counter: str, amount: int = 1) -> None:
        counters = state.get("counters", {})
        counters[counter] = int(counters.get(counter, 0)) + amount
        state.set("counters", counters)

    def _warn(self, message: str) -> None:
        if self._on_error:
            self._on_error(message)


def repair_session(config: Config, workflow_id: str) -> list[dict[str, Any]]:
    """Close a session whose harness exited without a session-end event.

    Emits the dangling turn (if any) and a terminal workflow record so the
    buffer is complete even after a crash or a ``kill -9``.
    """
    state_path = config.state_path(workflow_id)
    if not state_path.exists():
        return []

    recorder = Recorder(config)
    with session_state(state_path) as state:
        if state.get("ended_at"):
            return []
        event = HarnessEvent(
            kind=EventKind.SESSION_END,
            harness=state.get("harness") or "unknown",
            session_id=state.get("session_id") or workflow_id,
            timestamp=time.time(),
            source="repaired",
        )
        records = recorder._on_session_end(event, workflow_id, state)

    if records:
        Emitter(config, workflow_id).emit(*records, supersede=frozenset(recorder._supersede) or None)
    return records
