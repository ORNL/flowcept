"""
LangChain / LangGraph provenance capture through FlowceptCallbackHandler.

A prompt-template -> chat-model chain is invoked twice with the handler passed
as a callback. Each root chain run becomes a turn, and each chat-model run
becomes an ``ai_model_invocation`` task, recorded as PROV-AGENT provenance in a
JSONL buffer under ``~/.flowcept/harness/buffers/``.

The chat model is ``GenericFakeChatModel`` from langchain-core, so this example
runs fully offline — no API key needed. Swap in ChatOpenAI / ChatAnthropic (or
pass the handler to ``graph.invoke`` for LangGraph) and nothing else changes.

Run
---
    python examples/agents/langchain/langchain_example.py

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

No explicit start/stop calls are needed: the handler opens the session when it
is created and closes it when used as a context manager (or via ``close()``).
"""

from __future__ import annotations

import sys
import uuid

from flowcept.agents.langchain.langchain_plugin import FlowceptCallbackHandler

try:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.prompts import ChatPromptTemplate
except ImportError:
    print("ERROR: pip install langchain-core", file=sys.stderr)
    sys.exit(1)


def build_chain():
    """Build a prompt-template -> chat-model chain with canned responses."""
    model = GenericFakeChatModel(
        messages=iter(
            [
                AIMessage(content="A counter incremented 5 times with steps 1..5 reaches 15."),
                AIMessage(content="15 is the 5th triangular number: 1+2+3+4+5."),
            ]
        )
    )
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", "You are a concise data analyst."),
            ("human", "{question}"),
        ]
    )
    return prompt | model


def main():
    """Run two turns through the chain, capturing provenance for each."""
    chain = build_chain()
    session_id = f"langchain-example-{uuid.uuid4().hex[:8]}"

    # The handler is duck-typed against LangChain's callback protocol: the root
    # chain run opens a turn, the chat-model run inside it is recorded as an
    # ai_model_invocation, and closing the handler closes the session.
    with FlowceptCallbackHandler(session_id=session_id, model="fake-chat-model") as handler:
        for question in (
            "A counter was incremented 5 times with values 1, 2, 3, 4, 5. What is the final value?",
            "Why is that value 15?",
        ):
            print(f"\n[example] Question: {question}", flush=True)
            answer = chain.invoke({"question": question}, config={"callbacks": [handler]})
            print(f"[example] Answer  : {answer.content}", flush=True)

    print(f"\n[example] Captured session {session_id!r}. Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
