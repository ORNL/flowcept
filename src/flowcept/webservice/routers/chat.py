"""Chat endpoint: LLM with DB-backed provenance tools, streamed over SSE or as one JSON."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT, AGENT_CHAT_ENABLED
from flowcept.webservice.services.chat_orchestrator_service import run_chat

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatMessage(BaseModel):
    """One conversation message."""

    role: str
    content: str


class ChatRequest(BaseModel):
    """Chat request: client-passed history plus UI context."""

    messages: List[ChatMessage] = Field(min_length=1)
    context: Optional[Dict[str, Any]] = None
    stream: bool = True
    allow_dashboard_edit: bool = False
    thread_id: Optional[str] = None


def get_chat_llm():
    """Build the chat LLM from the existing ``agent`` settings; 503 when unavailable."""
    if not AGENT_CHAT_ENABLED:
        raise HTTPException(
            status_code=503,
            detail=(
                "Chat features are disabled. To enable them, set 'agent.chat_enabled: true' in your settings.yaml file."
            ),
        )
    api_key = AGENT.get("api_key")
    if not api_key or api_key in ("?", "your-api-key-here"):
        raise HTTPException(
            status_code=503,
            detail=(
                "LLM service is not configured. Please edit the 'agent' section in your settings.yaml file "
                "to provide a valid API key (e.g. replace 'your-api-key-here' with your real key), "
                "and ensure 'service_provider' and 'model' match your LLM provider configuration."
            ),
        )
    try:
        from flowcept.agents.llm.builders import build_llm_model

        return build_llm_model(track_tools=False)
    except HTTPException:
        raise
    except Exception as e:
        FlowceptLogger().exception(e)
        raise HTTPException(
            status_code=503,
            detail=(
                f"Could not initialize the LLM client using the configured settings: {e}. "
                "Please verify your credentials, API URL, and internet connection."
            ),
        ) from e


@router.post("")
def chat(payload: ChatRequest):
    """Answer a provenance chat message, optionally streaming SSE events.

    Streaming events: ``tool_call``, ``tool_result``, ``card``, ``token``, ``done``, ``error``.
    Non-streaming responses collect the same events into
    ``{"message", "tool_trace", "cards"}``.
    """
    llm = get_chat_llm()
    messages = [m.model_dump() for m in payload.messages]

    events = run_chat(
        llm,
        messages=messages,
        context=payload.context,
        allow_dashboard_edit=payload.allow_dashboard_edit,
    )

    if payload.stream:

        def sse_events():
            for event in events:
                yield {"event": event["event"], "data": json.dumps(event.get("data"), default=str)}

        return EventSourceResponse(sse_events(), ping=15)

    message_parts: List[str] = []
    tool_trace: List[Dict[str, Any]] = []
    cards: List[Dict[str, Any]] = []
    error: Optional[str] = None
    for event in events:
        if event["event"] == "token":
            message_parts.append(str(event.get("data", "")))
        elif event["event"] in ("tool_call", "tool_result"):
            tool_trace.append({"event": event["event"], **(event.get("data") or {})})
        elif event["event"] == "card":
            cards.append(event.get("data") or {})
        elif event["event"] == "error":
            error = str(event.get("data"))
    if error and not message_parts:
        raise HTTPException(status_code=500, detail=error)
    return {"message": "".join(message_parts), "tool_trace": tool_trace, "cards": cards}
