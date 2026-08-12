"""Unit tests for east-west identity forwarding (flowcept.agents.llm.request_identity).

Pure-logic tests — no cluster, MQ, or LLM. They verify that the ASGI middleware captures
Kong's ``X-Id-Token`` into the request-scoped ContextVar, that ``llm_forward_headers()``
reflects it, that the ContextVar is reset once the request finishes, and that non-HTTP
scopes (lifespan/websocket) pass through without setting any identity.
"""

import asyncio
import unittest

from flowcept.agents.llm.request_identity import (
    IdentityHeaderASGIMiddleware,
    get_id_token,
    llm_forward_headers,
    reset_id_token,
    set_id_token,
)


async def _noop_receive():
    return {"type": "http.request"}


async def _noop_send(_message):
    return None


def _run_through_middleware(headers=None, scope_type="http"):
    """Drive the middleware once and return what the downstream app observed.

    The before/after ContextVar reads happen inside the *same* coroutine/task as the
    middleware, so the middleware's set-then-reset is actually observable (an asyncio
    Task runs in a copied context, so reads from the outer thread would not be).
    """
    observed = {}

    async def capture_app(scope, receive, send):
        observed["scope_type"] = scope["type"]
        observed["token_in_app"] = get_id_token()
        observed["forward_in_app"] = llm_forward_headers()

    mw = IdentityHeaderASGIMiddleware(capture_app)
    scope = {"type": scope_type}
    if headers is not None:
        scope["headers"] = headers

    async def _drive():
        observed["token_before"] = get_id_token()
        await mw(scope, _noop_receive, _noop_send)
        observed["token_after"] = get_id_token()

    asyncio.run(_drive())
    return observed


class TestRequestIdentity(unittest.TestCase):
    def setUp(self):
        # Clean baseline for each test; restore afterwards.
        token = set_id_token(None)
        self.addCleanup(reset_id_token, token)

    def test_forwards_x_id_token_when_present(self):
        obs = _run_through_middleware([(b"x-id-token", b"tok-abc123")])
        self.assertEqual(obs["token_in_app"], "tok-abc123")
        self.assertEqual(obs["forward_in_app"], {"X-Id-Token": "tok-abc123"})

    def test_no_header_means_no_forward(self):
        obs = _run_through_middleware([(b"content-type", b"application/json")])
        self.assertIsNone(obs["token_in_app"])
        self.assertEqual(obs["forward_in_app"], {})

    def test_context_var_reset_after_request(self):
        obs = _run_through_middleware([(b"x-id-token", b"tok-xyz")])
        # Set while the app ran...
        self.assertEqual(obs["token_in_app"], "tok-xyz")
        # ...and restored to the prior state once the request finished.
        self.assertIsNone(obs["token_before"])
        self.assertIsNone(obs["token_after"])

    def test_non_http_scope_passes_through_untouched(self):
        # lifespan/websocket scopes must reach the app without setting identity.
        obs = _run_through_middleware(
            [(b"x-id-token", b"tok-should-be-ignored")], scope_type="lifespan"
        )
        self.assertEqual(obs["scope_type"], "lifespan")
        self.assertIsNone(obs["token_in_app"])
        self.assertEqual(obs["forward_in_app"], {})

    def test_missing_headers_key_is_safe(self):
        # scope may omit "headers" entirely; the middleware must not raise.
        obs = _run_through_middleware(headers=None)
        self.assertIsNone(obs["token_in_app"])
        self.assertEqual(obs["forward_in_app"], {})

    def test_llm_forward_headers_reads_current_context(self):
        self.assertEqual(llm_forward_headers(), {})
        token = set_id_token("direct-set")
        try:
            self.assertEqual(get_id_token(), "direct-set")
            self.assertEqual(llm_forward_headers(), {"X-Id-Token": "direct-set"})
        finally:
            reset_id_token(token)
        self.assertEqual(llm_forward_headers(), {})

    def test_empty_token_string_does_not_forward(self):
        # An empty X-Id-Token value must not produce a header (guards against
        # forwarding a meaningless empty identity).
        token = set_id_token("")
        try:
            self.assertEqual(llm_forward_headers(), {})
        finally:
            reset_id_token(token)


if __name__ == "__main__":
    unittest.main()
