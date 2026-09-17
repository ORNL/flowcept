"""
OpenAI Agents SDK provenance capture through FlowceptTraceProcessor.

The Agents SDK already traces itself — every run produces a trace of typed
spans — and ``install()`` registers Flowcept as one more consumer of those
spans. Nothing about how you call the SDK changes.

Two modes:

* ``OPENAI_API_KEY`` set   : run a real agent with ``Runner.run_sync`` — the
                             trace it produces is captured automatically.
* no key (offline)         : drive the SDK's own tracing API directly
                             (``trace`` / ``generation_span`` /
                             ``function_span``), which exercises exactly the
                             same capture path without any API call.

Either way the session lands as PROV-AGENT provenance in a JSONL buffer under
``~/.flowcept/harness/buffers/``.

Run
---
    python examples/agents/openai_agents/openai_agents_example.py                    # offline
    OPENAI_API_KEY=sk-... python examples/agents/openai_agents/openai_agents_example.py

Then inspect the capture:

    flowcept-harness sessions
    flowcept-harness show
    flowcept-harness report

Plugin configuration
--------------------
The harness plugins are configured with environment variables, not
settings.yaml (see src/flowcept/agents/harness/README.md for the full table):

    FLOWCEPT_HARNESS_ENABLED=1        # master switch (default)
    FLOWCEPT_HARNESS_ONLINE=0         # 1 publishes to a live Flowcept backend
    FLOWCEPT_HARNESS_REDACT=1         # redact credential-shaped values

``install()`` adds Flowcept alongside the SDK's own trace exporter;
``install(replace=True)`` makes Flowcept the only consumer (used in the
offline mode below so the SDK does not try to export to OpenAI).
"""

from __future__ import annotations

import os
import sys
import uuid

from flowcept.agents.openai_agents.openai_agents_plugin import install

try:
    from agents.tracing import function_span, generation_span, trace
except ImportError:
    print("ERROR: pip install openai-agents", file=sys.stderr)
    sys.exit(1)


def run_with_api_key():
    """Run a real agent; its trace is captured by the installed processor."""
    from agents import Agent, Runner

    install()  # register once, nothing else changes

    agent = Agent(
        name="counter-analyst",
        instructions="You are a concise data analyst.",
        model="gpt-4o-mini",
    )
    result = Runner.run_sync(
        agent,
        "A counter was incremented 5 times with values 1, 2, 3, 4, 5. "
        "In one sentence, what does the final value 15 represent?",
    )
    print(f"\n[example] Agent says: {result.final_output}", flush=True)


def run_offline():
    """Emit a synthetic trace through the SDK's tracing API — no API call."""
    # replace=True: Flowcept becomes the only trace consumer, so the SDK does
    # not also try to export the trace to OpenAI's backend.
    install(replace=True)

    session_id = f"openai-agents-example-{uuid.uuid4().hex[:8]}"

    # `group_id` is the SDK's conversation id; the plugin uses it as the
    # provenance session id, so a multi-turn conversation is one session.
    with trace("counter-run", group_id=session_id):
        with function_span("increment_counter", input='{"steps": [1, 2, 3, 4, 5]}') as tool:
            tool.span_data.output = '{"total": 15}'
        with generation_span(
            model="gpt-4o-mini",
            input=[{"role": "user", "content": "What does the counter total 15 represent?"}],
            output=[{"role": "assistant", "content": "15 is the sum 1+2+3+4+5 — the 5th triangular number."}],
            usage={"input_tokens": 25, "output_tokens": 18},
        ):
            pass

    print(f"\n[example] Captured synthetic session {session_id!r} (offline mode).", flush=True)


def main():
    """Capture one OpenAI Agents SDK session, real or synthetic."""
    if os.getenv("OPENAI_API_KEY"):
        run_with_api_key()
    else:
        print("[example] OPENAI_API_KEY not set — emitting synthetic SDK spans instead.", flush=True)
        run_offline()

    print("\n[example] Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
