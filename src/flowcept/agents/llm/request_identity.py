"""Per-request caller-identity propagation for east-west LLM calls.

When Flowcept is fronted by the AmSC Kong gateway, Kong validates the caller's AmSC PAT
and injects a trusted ``X-Id-Token`` header (base64-encoded id token) on the request that
reaches the webservice / MCP agent. For LLM calls we forward that token *verbatim* to the
MAG (LiteLLM) proxy, which authenticates on it and attributes usage to the caller's user +
project context — so Flowcept holds no shared LLM key.

Mechanism: a request-scoped ``ContextVar`` is set by a pure-ASGI middleware (one per server
process) and read by ``build_llm_model`` when it constructs the OpenAI-compatible client.
Because ``build_llm_model`` is called fresh per tool-call / per chat request, each request's
client carries only its own caller's token — no cross-request leakage.

Off-gateway (local dev, non-Kong deployments): no ``X-Id-Token`` header is present, the
ContextVar stays ``None``, and no identity header is added — behavior is unchanged.
"""

from contextvars import ContextVar, Token
from typing import Optional

# ASGI lower-cases header names; Kong injects "X-Id-Token".
_ID_TOKEN_HEADER = b"x-id-token"

# Forwarded on the outbound LLM request (MAG reads this exact header name).
_FORWARD_HEADER = "X-Id-Token"

_id_token_var: ContextVar[Optional[str]] = ContextVar("flowcept_x_id_token", default=None)


def set_id_token(token: Optional[str]) -> Token:
    """Set the current request's X-Id-Token; returns a reset token for teardown."""
    return _id_token_var.set(token)


def reset_id_token(token: Token) -> None:
    """Restore the previous ContextVar state (call in a ``finally``)."""
    _id_token_var.reset(token)


def get_id_token() -> Optional[str]:
    """Return the current request's forwarded X-Id-Token, or None if off-gateway."""
    return _id_token_var.get()


def llm_forward_headers() -> dict:
    """Headers to attach to an outbound LLM call so MAG attributes usage to the caller.

    Returns ``{"X-Id-Token": <token>}`` when a token is present on this request, else ``{}``
    (so off-gateway calls are unaffected).
    """
    token = _id_token_var.get()
    return {_FORWARD_HEADER: token} if token else {}


class IdentityHeaderASGIMiddleware:
    """Capture Kong's trusted ``X-Id-Token`` into the request-scoped ContextVar.

    Pure ASGI (not Starlette ``BaseHTTPMiddleware``) on purpose: BaseHTTPMiddleware runs the
    downstream app in a separate task, which breaks ContextVar propagation to the endpoint.
    A pure-ASGI middleware sets the ContextVar in the same task that runs the app, so the
    value is visible to tool functions / chat handlers and thus to ``build_llm_model``.

    Wraps both the FastMCP ``streamable_http_app`` (agent) and the FastAPI app (webservice).
    Non-HTTP scopes (lifespan, websocket) pass straight through.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        token = None
        for name, value in scope.get("headers") or []:
            if name == _ID_TOKEN_HEADER:
                token = value.decode("latin-1")
                break
        reset = set_id_token(token)
        try:
            await self.app(scope, receive, send)
        finally:
            reset_id_token(reset)
