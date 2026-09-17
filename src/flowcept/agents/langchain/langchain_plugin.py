"""LangChain and LangGraph wrapper.

LangChain's callback protocol is already the right shape for provenance: every
run reports a start, an end, its own ``run_id``, and its ``parent_run_id``.
LangGraph uses the same protocol, so one handler covers both.

    from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler

    handler = FlowceptCallbackHandler(session_id="thread-42")
    graph.invoke({"messages": [...]}, config={"callbacks": [handler]})

What each run becomes:

=====================  ==================================================
root chain / graph     the turn — its inputs are the prompt, its outputs
                       the response
nested chain / node    structure only, no record of its own
LLM / chat model       ``ai_model_invocation`` at call granularity
tool                   ``agent_tool``
retriever              ``agent_tool`` (a retrieval is a tool execution)
=====================  ==================================================

Nested chains are deliberately not recorded. LangGraph emits a run per node,
per branch, and per internal ``RunnableSequence``, and turning all of that into
tasks would bury the model calls and tool calls that actually describe what the
agent did. The graph's structure is still recoverable: every recorded task
carries its enclosing turn.

Duck-typed rather than subclassing ``BaseCallbackHandler`` -- nothing here
imports langchain, so it works against any 0.1+ version and imports without
langchain installed. The ``ignore_*`` and ``raise_error`` attributes below are
part of that contract: the callback manager reads them off the handler.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from flowcept.agents.harness.config import Config
from flowcept.agents.harness.tracer import SessionTracer


class FlowceptCallbackHandler:
    """A LangChain callback handler that records Flowcept provenance."""

    # -- the attributes langchain's callback manager reads off a handler -----
    ignore_llm = False
    ignore_chain = False
    ignore_agent = False
    ignore_retriever = False
    ignore_chat_model = False
    ignore_retry = True
    ignore_custom_event = True
    raise_error = False
    run_inline = False

    def __init__(
        self,
        session_id: str | None = None,
        *,
        config: Config | None = None,
        harness: str = "langchain",
        model: str | None = None,
        tracer: SessionTracer | None = None,
    ):
        self.tracer = tracer or SessionTracer(harness, session_id, config=config, model=model)
        self.tracer.start()
        #: The run that owns the current turn; ``None`` between turns.
        self._turn_run: str | None = None
        #: run_id -> tool name, so an end callback can name what it closes.
        self._tools: dict[str, str] = {}
        #: run_id -> model name, likewise for LLM runs.
        self._models: dict[str, str | None] = {}
        self._prompts: dict[str, str | None] = {}

    # -- chains / graphs -----------------------------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any] | None,
        inputs: Any,
        *,
        run_id: UUID | None = None,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Open a turn when a root chain or graph run starts."""
        if parent_run_id is not None or self._turn_run is not None:
            return  # nested run: structure only
        self._open_turn(_key(run_id), _as_text(_unwrap_input(inputs)))

    def on_chain_end(self, outputs: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Close the turn with the root chain's outputs as the response."""
        if self._turn_run != _key(run_id):
            return
        self._close_turn(response=_as_text(_unwrap_output(outputs)))

    def on_chain_error(self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Close the turn with the root chain's error."""
        if self._turn_run != _key(run_id):
            return
        self._close_turn(error=_error_text(error))

    # -- models --------------------------------------------------------------

    def on_llm_start(
        self,
        serialized: dict[str, Any] | None,
        prompts: list[str] | None,
        *,
        run_id: UUID | None = None,
        parent_run_id: UUID | None = None,
        invocation_params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Remember the model and prompt of a starting LLM run."""
        key = _key(run_id)
        model = _model_name(serialized, invocation_params, kwargs)
        self._models[key] = model
        self._prompts[key] = "\n\n".join(p for p in (prompts or []) if isinstance(p, str)) or None
        if parent_run_id is None and self._turn_run is None:
            # A model invoked directly, with no chain around it: that call is
            # the whole turn.
            self._open_turn(key, self._prompts[key])

    def on_chat_model_start(
        self,
        serialized: dict[str, Any] | None,
        messages: Any,
        *,
        run_id: UUID | None = None,
        parent_run_id: UUID | None = None,
        invocation_params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Handle a starting chat-model run as an LLM run with flattened messages."""
        self.on_llm_start(
            serialized,
            [_messages_text(messages)] if messages is not None else None,
            run_id=run_id,
            parent_run_id=parent_run_id,
            invocation_params=invocation_params,
            **kwargs,
        )

    def on_llm_end(self, response: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Record the completed LLM run as an ``ai_model_invocation`` task."""
        key = _key(run_id)
        model, usage = _llm_result_details(response)
        self.tracer.llm_call(
            model=model or self._models.pop(key, None),
            prompt=self._prompts.pop(key, None),
            response=_generations_text(response),
            usage=usage,
            call_id=key,
        )
        self._models.pop(key, None)
        if self._turn_run == key:
            self._close_turn(response=_generations_text(response))

    def on_llm_error(self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Record the failed LLM run with its error text."""
        key = _key(run_id)
        self.tracer.llm_call(
            model=self._models.pop(key, None),
            prompt=self._prompts.pop(key, None),
            call_id=key,
            error=_error_text(error),
        )
        if self._turn_run == key:
            self._close_turn(error=_error_text(error))

    # -- tools and retrievers ------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any] | None,
        input_str: str | None,
        *,
        run_id: UUID | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Record the start of a tool run as an ``agent_tool`` task."""
        key = _key(run_id)
        name = (serialized or {}).get("name") or "tool"
        self._tools[key] = name
        self.tracer.tool_start(name, inputs if inputs is not None else input_str, tool_use_id=key)

    def on_tool_end(self, output: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Close the tool run's task with its output."""
        key = _key(run_id)
        self.tracer.tool_end(key, name=self._tools.pop(key, None), tool_response=_jsonable(output))

    def on_tool_error(self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Close the tool run's task with its error."""
        key = _key(run_id)
        self.tracer.tool_end(key, name=self._tools.pop(key, None), error=_error_text(error))

    def on_retriever_start(
        self,
        serialized: dict[str, Any] | None,
        query: str | None,
        *,
        run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        """Record the start of a retriever run as an ``agent_tool`` task."""
        key = _key(run_id)
        name = (serialized or {}).get("name") or "retriever"
        self._tools[key] = name
        self.tracer.tool_start(name, {"query": query}, tool_use_id=key)

    def on_retriever_end(self, documents: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Close the retriever run's task with the retrieved documents."""
        key = _key(run_id)
        self.tracer.tool_end(
            key,
            name=self._tools.pop(key, None),
            tool_response={"documents": [_document(d) for d in documents or []]},
        )

    def on_retriever_error(self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        """Close the retriever run's task with its error."""
        key = _key(run_id)
        self.tracer.tool_end(key, name=self._tools.pop(key, None), error=_error_text(error))

    # -- agents --------------------------------------------------------------

    def on_agent_action(self, action: Any, **kwargs: Any) -> None:
        """No record: the tool callbacks already cover the action itself."""

    def on_agent_finish(self, finish: Any, **kwargs: Any) -> None:
        """No record: the enclosing chain's end closes the turn."""

    def on_text(self, text: str, **kwargs: Any) -> None:
        """No record: intermediate text is not an activity."""

    # -- teardown ------------------------------------------------------------

    def close(self, *, error: str | None = None) -> None:
        """Close open runs and the session. Safe to call more than once."""
        for key, name in list(self._tools.items()):
            self.tracer.tool_end(key, name=name, error="never returned a result")
        self._tools.clear()
        if self._turn_run is not None:
            self._close_turn(error=error)
        self.tracer.end(source="error" if error else "completed")

    def __enter__(self) -> FlowceptCallbackHandler:
        """Return the handler itself for use as a context manager."""
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Close the session, recording the in-flight exception if any."""
        self.close(error=f"{exc_type.__name__}: {exc}" if exc_type else None)
        return False

    # -- turns ---------------------------------------------------------------

    def _open_turn(self, key: str, prompt: str | None) -> None:
        self._turn_run = key
        self.tracer.prompt(prompt, prompt_id=key)

    def _close_turn(self, *, response: str | None = None, error: str | None = None) -> None:
        self._turn_run = None
        self.tracer.turn_end(response=response, error=error)


# -- readers for langchain's loosely-typed callback payloads ------------------


def _key(run_id: Any) -> str:
    return str(run_id) if run_id is not None else "root"


def _unwrap_input(inputs: Any) -> Any:
    """Pull the interesting part out of a chain's input mapping."""
    if isinstance(inputs, dict):
        for field in ("input", "question", "messages", "query"):
            if field in inputs:
                return inputs[field]
    return inputs


def _unwrap_output(outputs: Any) -> Any:
    if isinstance(outputs, dict):
        for field in ("output", "answer", "messages", "result"):
            if field in outputs:
                return outputs[field]
    return outputs


def _model_name(serialized: Any, invocation_params: Any, kwargs: dict[str, Any]) -> str | None:
    for source in (invocation_params, kwargs.get("metadata"), serialized):
        if isinstance(source, dict):
            for field in ("model", "model_name", "model_id", "ls_model_name"):
                value = source.get(field)
                if isinstance(value, str):
                    return value
    if isinstance(serialized, dict):
        # Fall back to the class the callback came from, e.g. ChatAnthropic.
        identifier = serialized.get("id")
        if isinstance(identifier, list) and identifier:
            return str(identifier[-1])
    return None


def _llm_result_details(response: Any) -> tuple[str | None, dict[str, Any] | None]:
    output = getattr(response, "llm_output", None)
    model = None
    usage = None
    if isinstance(output, dict):
        model = output.get("model_name") or output.get("model")
        for field in ("token_usage", "usage", "usage_metadata"):
            candidate = output.get(field)
            if isinstance(candidate, dict):
                usage = candidate
                break
    if usage is None:
        # Newer versions carry usage on the generation's message instead.
        message = _first_generation_attribute(response, "message")
        candidate = getattr(message, "usage_metadata", None)
        if isinstance(candidate, dict):
            usage = candidate
    return (model if isinstance(model, str) else None), usage


def _generations_text(response: Any) -> str | None:
    text = _first_generation_attribute(response, "text")
    if isinstance(text, str) and text:
        return text
    message = _first_generation_attribute(response, "message")
    content = getattr(message, "content", None)
    return _as_text(content) if content is not None else None


def _first_generation_attribute(response: Any, attribute: str) -> Any:
    generations = getattr(response, "generations", None)
    if not isinstance(generations, list):
        return None
    for group in generations:
        items = group if isinstance(group, list) else [group]
        for item in items:
            value = getattr(item, attribute, None)
            if value is not None:
                return value
    return None


def _messages_text(messages: Any) -> str:
    """Flatten the nested list of chat messages a chat model is started with."""
    parts: list[str] = []
    groups = messages if isinstance(messages, list) else [messages]
    for group in groups:
        items = group if isinstance(group, list) else [group]
        for message in items:
            content = getattr(message, "content", message)
            role = getattr(message, "type", None) or getattr(message, "role", None)
            text = _as_text(content) or ""
            parts.append(f"{role}: {text}" if role else text)
    return "\n".join(parts)


def _document(document: Any) -> dict[str, Any]:
    return {
        "page_content": getattr(document, "page_content", None),
        "metadata": _jsonable(getattr(document, "metadata", None)),
    }


def _error_text(error: BaseException | Any) -> str:
    if isinstance(error, BaseException):
        return f"{type(error).__name__}: {error}"
    return str(error)


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    for attribute in ("model_dump", "dict", "to_dict"):
        method = getattr(value, attribute, None)
        if callable(method):
            try:
                result = method()
            except Exception:
                continue
            if isinstance(result, dict):
                return result
    return repr(value)


def _as_text(value: Any) -> str | None:
    if value is None or isinstance(value, str):
        return value
    try:
        return json.dumps(_jsonable(value), default=repr)
    except (TypeError, ValueError):
        return repr(value)
