"""Claude Agent SDK wrapper.

The SDK hands you an async stream of message objects. Everything provenance
needs is already in that stream — tool uses, tool results, token usage, the
final answer — so capture is a matter of reading it as it goes past rather than
instrumenting anything.

    from flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin import trace_query

    async for message in trace_query(prompt="fix the failing test"):
        print(message)

:func:`trace_query` is a drop-in for ``claude_agent_sdk.query``: same
arguments, same yielded messages, provenance as a side effect. To capture a
``ClaudeSDKClient`` conversation instead, drive :class:`ClaudeAgentTracer`
directly with the messages you receive.

Messages are matched structurally, not with ``isinstance``. The SDK's block
classes have moved between versions and this module must import without the
SDK present at all, so it reads the shape it needs and ignores the rest.
"""

from __future__ import annotations

import json
from typing import Any

from flowcept.agents.harness.config import Config
from flowcept.agents.harness.tracer import SessionTracer

#: The tools the assistant uses to spawn a subagent. One gets a nested workflow
#: in addition to its tool record, so the subagent's work is attributable to it.
#: The name has changed across CLI versions ("Task", then "Agent"), so both are
#: recognized.
SUBAGENT_TOOLS = frozenset({"Task", "Agent"})

#: System-message subtypes that earn a record. The system stream is an open
#: channel: the CLI also uses it for progress tickers such as ``thinking_tokens``,
#: which arrive hundreds of times per turn, carry no provenance, and would
#: otherwise dwarf the session. Unlisted subtypes are ignored, the same way the
#: Claude Code hook adapter ignores hook events it has no mapping for.
RECORDED_SYSTEM_SUBTYPES = frozenset({"compact_boundary"})


class ClaudeAgentTracer:
    """Turns a Claude Agent SDK message stream into Flowcept provenance.

    Feed it every message the SDK yields, in order, then call :meth:`close`.
    One turn is opened per user prompt and closed by the ``ResultMessage``.
    """

    def __init__(
        self,
        session_id: str | None = None,
        *,
        config: Config | None = None,
        model: str | None = None,
        harness: str = "claude_agent_sdk",
        prompt: str | None = None,
        tracer: SessionTracer | None = None,
    ):
        self.tracer = tracer or SessionTracer(harness, session_id, config=config, model=model)
        self._open_turn = False
        self._pending_prompt = prompt
        #: tool_use_id -> tool name, so a result can name the tool it closes.
        self._tools: dict[str, str] = {}
        #: tool_use_id of Task calls, which also own a subagent workflow.
        self._subagents: dict[str, str] = {}
        self._text: list[str] = []
        #: Whether any record has been written yet. Until it has, the session
        #: id is still negotiable; see :meth:`_adopt_session_id`.
        self._emitted = False
        self._explicit_session_id = session_id is not None

    def _adopt_session_id(self, session_id: Any) -> None:
        """Take the SDK's session id, if it is not too late to.

        All provenance ids derive from the session id, so adopting the SDK's
        makes a resumed conversation continue the same workflow instead of
        forking a new one. Once a record has been written the id is load-
        bearing and changing it would orphan everything already emitted, so
        this only ever fires before the first one.
        """
        if self._emitted or self._explicit_session_id or not isinstance(session_id, str):
            return
        self.tracer.session_id = session_id

    def _ensure_started(self) -> None:
        if self._emitted:
            return
        self._emitted = True
        self.tracer.start()
        if self._pending_prompt is not None:
            self.begin_turn(self._pending_prompt)

    # -- turns ---------------------------------------------------------------

    def begin_turn(self, prompt: str | None = None) -> None:
        """Open a turn for a user prompt."""
        self._emitted = True
        self._text = []
        self._open_turn = True
        self._pending_prompt = None
        self.tracer.prompt(prompt)

    # -- the stream ----------------------------------------------------------

    def handle(self, message: Any) -> None:
        """Record one streamed message. Unknown messages are ignored."""
        kind = _message_kind(message)
        if kind == "system":
            # Handled first and without starting: the SDK's init message is
            # where the real session id arrives, ahead of everything else.
            self._on_system(message)
            return
        self._adopt_session_id(getattr(message, "session_id", None))
        self._ensure_started()
        if kind == "assistant":
            self._on_assistant(message)
        elif kind == "user":
            self._on_user(message)
        elif kind == "result":
            self._on_result(message)

    def _on_assistant(self, message: Any) -> None:
        model = getattr(message, "model", None)
        if model:
            self.tracer.model = model
        if not self._open_turn:
            self.begin_turn(self._pending_prompt)

        for block in _blocks(message):
            text = getattr(block, "text", None)
            if isinstance(text, str):
                self._text.append(text)
                continue

            name = getattr(block, "name", None)
            tool_use_id = getattr(block, "id", None)
            if not (name and tool_use_id):
                continue

            tool_input = getattr(block, "input", None)
            self._tools[tool_use_id] = name
            self.tracer.tool_start(name, tool_input, tool_use_id=tool_use_id)

            if name in SUBAGENT_TOOLS:
                arguments = tool_input if isinstance(tool_input, dict) else {}
                self._subagents[tool_use_id] = self.tracer.subagent_start(
                    arguments.get("subagent_type") or arguments.get("description") or "subagent",
                    agent_ref=tool_use_id,
                    prompt=arguments.get("prompt"),
                )

    def _on_user(self, message: Any) -> None:
        """A user message in the stream is the harness returning tool results."""
        for block in _blocks(message):
            tool_use_id = getattr(block, "tool_use_id", None)
            if not tool_use_id:
                continue
            content = getattr(block, "content", None)
            is_error = bool(getattr(block, "is_error", False))
            self.tracer.tool_end(
                tool_use_id,
                name=self._tools.pop(tool_use_id, None),
                tool_response=None if is_error else content,
                error=_as_text(content) if is_error else None,
            )
            if tool_use_id in self._subagents:
                self.tracer.subagent_stop(
                    self._subagents.pop(tool_use_id),
                    response=None if is_error else _as_text(content),
                    error=_as_text(content) if is_error else None,
                )

    def _on_result(self, message: Any) -> None:
        usage = _as_dict(getattr(message, "usage", None))
        cost = getattr(message, "total_cost_usd", None)
        if usage is not None and cost is not None:
            usage = {**usage, "total_cost_usd": cost}

        response = getattr(message, "result", None)
        if not isinstance(response, str):
            response = "".join(self._text) or None

        error = None
        if getattr(message, "is_error", False):
            error = _as_text(response) or "the SDK reported an error result"

        self.tracer.turn_end(response=response, usage=usage, error=error)
        self._open_turn = False
        self._text = []

    def _on_system(self, message: Any) -> None:
        subtype = getattr(message, "subtype", None)
        data = getattr(message, "data", None)
        if isinstance(data, dict):
            self._adopt_session_id(data.get("session_id"))
            model = data.get("model")
            if isinstance(model, str):
                self.tracer.model = model
        self._adopt_session_id(getattr(message, "session_id", None))

        if subtype == "init":
            # Nothing happened yet worth a record; the id and model were the
            # point of this message.
            return
        if subtype not in RECORDED_SYSTEM_SUBTYPES:
            return
        self._ensure_started()
        self.tracer.compact(source=subtype)

    # -- teardown ------------------------------------------------------------

    def close(self, *, error: str | None = None) -> None:
        """Close any open tool calls, the turn, and the session.

        A run that produced nothing at all is left unrecorded: an empty session
        is noise, not provenance. A run that had a prompt still gets one, since
        "we asked and got nothing back" is worth knowing.
        """
        if not self._emitted:
            if self._pending_prompt is None and error is None:
                return
            self._ensure_started()
        for tool_use_id, name in list(self._tools.items()):
            self.tracer.tool_end(tool_use_id, name=name, error="never returned a result")
        self._tools.clear()
        for ref in list(self._subagents.values()):
            self.tracer.subagent_stop(ref, error="never returned a result")
        self._subagents.clear()
        if self._open_turn:
            self.tracer.turn_end(response="".join(self._text) or None, error=error)
            self._open_turn = False
        self.tracer.end(source="error" if error else "completed")

    def __enter__(self) -> ClaudeAgentTracer:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close(error=f"{exc_type.__name__}: {exc}" if exc_type else None)
        return False


async def trace_query(prompt: Any, options: Any = None, *, config: Config | None = None, **kwargs: Any):
    """``claude_agent_sdk.query`` with provenance capture.

    Yields exactly what ``query`` yields; the capture is a side effect, so this
    can be substituted for the original call without changing the consumer.
    """
    from claude_agent_sdk import query  # imported here: the SDK is an extra

    tracer = ClaudeAgentTracer(
        config=config,
        prompt=prompt if isinstance(prompt, str) else None,
    )
    try:
        async for message in query(prompt=prompt, options=options, **kwargs):
            try:
                tracer.handle(message)
            except Exception:
                # Capture must never break the stream it is observing.
                pass
            yield message
    except BaseException as exc:
        tracer.close(error=f"{type(exc).__name__}: {exc}")
        raise
    else:
        tracer.close()


# -- structural message matching ---------------------------------------------


def _message_kind(message: Any) -> str | None:
    """Classify a message by class name, falling back to its shape."""
    name = type(message).__name__
    for candidate in ("Assistant", "User", "Result", "System"):
        if name.startswith(candidate):
            return candidate.lower()

    if hasattr(message, "num_turns") or hasattr(message, "total_cost_usd"):
        return "result"
    if hasattr(message, "data") and hasattr(message, "subtype"):
        return "system"
    if hasattr(message, "content"):
        # Only the assistant's messages name the model that produced them.
        return "assistant" if getattr(message, "model", None) else "user"
    return None


def _blocks(message: Any) -> list[Any]:
    content = getattr(message, "content", None)
    if isinstance(content, list):
        return content
    if isinstance(content, str):
        return [_TextBlock(content)]
    return []


class _TextBlock:
    """Wraps bare string content so callers see one uniform block shape."""

    __slots__ = ("text",)

    def __init__(self, text: str):
        self.text = text


def _as_dict(value: Any) -> dict[str, Any] | None:
    if value is None or isinstance(value, dict):
        return value
    for attribute in ("model_dump", "to_dict", "_asdict"):
        method = getattr(value, attribute, None)
        if callable(method):
            try:
                result = method()
            except Exception:
                continue
            if isinstance(result, dict):
                return result
    return getattr(value, "__dict__", None) or None


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    if isinstance(value, list):
        # Tool results arrive as content blocks; keep the text, drop the rest.
        parts = [b.get("text") if isinstance(b, dict) else getattr(b, "text", None) for b in value]
        joined = "".join(p for p in parts if isinstance(p, str))
        if joined:
            return joined
    try:
        return json.dumps(value, default=repr)
    except (TypeError, ValueError):
        return repr(value)
