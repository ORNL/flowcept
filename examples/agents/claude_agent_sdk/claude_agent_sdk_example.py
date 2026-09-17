"""
Claude Agent SDK provenance capture through trace_query.

``trace_query`` is a drop-in for ``claude_agent_sdk.query``: same arguments,
same yielded messages, provenance as a side effect. The SDK hands you an async
stream of message objects, and everything provenance needs — tool uses, tool
results, token usage, the final answer — is already in that stream, so
swapping ``query`` for ``trace_query`` is the entire integration. (To capture
a ``ClaudeSDKClient`` conversation instead, drive ``ClaudeAgentTracer``
directly with the messages you receive.)

The example asks one question with a single-turn budget and no tools, prints
the streamed answer, and leaves the session as PROV-AGENT provenance in a
JSONL buffer under ``~/.flowcept/harness/buffers/``.

Run
---
    ANTHROPIC_API_KEY=sk-ant-... python examples/agents/claude_agent_sdk/claude_agent_sdk_example.py

Requires the Claude Agent SDK: ``pip install "flowcept[harness_claude_sdk]"``
(or ``pip install claude-agent-sdk``).

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
"""

from __future__ import annotations

import asyncio
import os
import sys

from flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin import trace_query

try:
    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, CLINotFoundError, ResultMessage
except ImportError:
    print('ERROR: pip install "flowcept[harness_claude_sdk]"  (or: pip install claude-agent-sdk)', file=sys.stderr)
    sys.exit(1)


async def run() -> None:
    """Ask one question through trace_query and print the streamed answer."""
    options = ClaudeAgentOptions(
        max_turns=1,
        allowed_tools=[],  # a pure Q&A turn; tool use would be captured too
        system_prompt="You are a concise data analyst.",
    )

    prompt = (
        "A counter was incremented 5 times with values 1, 2, 3, 4, 5 and reached 15. "
        "In exactly one sentence, explain what this arithmetic result represents."
    )
    print(f"\n[example] Prompt: {prompt}\n", flush=True)

    # trace_query yields exactly what claude_agent_sdk.query yields; the
    # provenance capture is a side effect.
    async for message in trace_query(prompt=prompt, options=options):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                text = getattr(block, "text", None)
                if isinstance(text, str):
                    print(f"[example] Claude: {text}", flush=True)
        elif isinstance(message, ResultMessage):
            print(f"\n[example] Turns: {message.num_turns}, cost: ${message.total_cost_usd or 0:.4f}", flush=True)


def main():
    """Check credentials, then run the traced query."""
    if not os.getenv("ANTHROPIC_API_KEY"):
        print(
            "ERROR: ANTHROPIC_API_KEY is not set.\n"
            "This example calls the Claude API through the Claude Agent SDK.\n"
            "Set the key and re-run:\n"
            "  ANTHROPIC_API_KEY=sk-ant-... python examples/agents/claude_agent_sdk/claude_agent_sdk_example.py",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        asyncio.run(run())
    except CLINotFoundError:
        print(
            "ERROR: the Claude Code CLI the SDK drives was not found.\n"
            "Install it with:  npm install -g @anthropic-ai/claude-code",
            file=sys.stderr,
        )
        sys.exit(1)

    print("\n[example] Captured. Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
