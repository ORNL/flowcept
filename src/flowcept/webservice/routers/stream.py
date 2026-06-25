"""SSE endpoints streaming new/updated tasks and workflows via incremental DB polling."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import anyio
from fastapi import APIRouter, Depends, Query, Request
from sse_starlette.sse import EventSourceResponse

from flowcept.configs import WEBSERVER_SSE_MAX_BATCH, WEBSERVER_SSE_POLL_INTERVAL
from flowcept.flowcept_api.db_api import DBAPI
from flowcept.webservice.deps import get_db_api
from flowcept.webservice.services.serializers import normalize_docs
from flowcept.webservice.services.streaming import poll_new_docs

router = APIRouter(prefix="/stream", tags=["stream"])


def _event_stream(
    request: Request,
    db: DBAPI,
    collection: str,
    base_filter: Dict[str, Any],
    since: float,
    poll_interval: float,
):
    """Async generator yielding one SSE event per poll that finds new documents."""
    payload_key = collection  # "tasks" or "workflows"

    async def generator():
        cursor = since
        while not await request.is_disconnected():
            docs, new_cursor, truncated = await anyio.to_thread.run_sync(
                poll_new_docs, db, collection, base_filter, cursor, WEBSERVER_SSE_MAX_BATCH
            )
            if docs:
                cursor = new_cursor
                yield {
                    "event": payload_key,
                    "data": json.dumps({payload_key: normalize_docs(docs), "cursor": cursor, "truncated": truncated}),
                }
            await anyio.sleep(poll_interval)

    return generator()


@router.get("/tasks")
def stream_tasks(
    request: Request,
    workflow_id: Optional[str] = None,
    campaign_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    since: Optional[float] = None,
    poll_interval: float = Query(default=WEBSERVER_SSE_POLL_INTERVAL, ge=0.1, le=60.0),
    db: DBAPI = Depends(get_db_api),
) -> EventSourceResponse:
    """Stream new/updated tasks as SSE events, optionally scoped by workflow/campaign/agent."""
    base_filter: Dict[str, Any] = {}
    for key, value in (("workflow_id", workflow_id), ("campaign_id", campaign_id), ("agent_id", agent_id)):
        if value is not None:
            base_filter[key] = value
    cursor = time.time() if since is None else since
    return EventSourceResponse(_event_stream(request, db, "tasks", base_filter, cursor, poll_interval), ping=15)


@router.get("/workflows")
def stream_workflows(
    request: Request,
    campaign_id: Optional[str] = None,
    since: Optional[float] = None,
    poll_interval: float = Query(default=WEBSERVER_SSE_POLL_INTERVAL, ge=0.1, le=60.0),
    db: DBAPI = Depends(get_db_api),
) -> EventSourceResponse:
    """Stream new workflows as SSE events, optionally scoped by campaign."""
    base_filter: Dict[str, Any] = {}
    if campaign_id is not None:
        base_filter["campaign_id"] = campaign_id
    cursor = time.time() if since is None else since
    return EventSourceResponse(_event_stream(request, db, "workflows", base_filter, cursor, poll_interval), ping=15)
