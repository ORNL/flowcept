"""
examples/agents/autogen/autogen_example.py
==========================================

Counter test mirroring the Academy example:

  AssistantAgent  : increments a counter 5 times (values 1-5)
  CriticAgent     : verifies each running total
  interpret step  : calls llm_chat() inside _run() to interpret the final
                    value (15 = 1+2+3+4+5), mirroring SummaryAgent.interpret_result()

Run
---
    OPENAI_API_KEY=sk-... (or ANTHROPIC_API_KEY=sk-ant-...) python examples/agents/autogen/autogen_example.py

Plugin configuration
--------------------
Enable the AutoGen plugin in your settings.yaml:

    plugins:
      autogen:
        enabled: true
        kind: autogen
        workflow_name: "autogen-counter-test"
        performance_tracking: true

Flowcept will auto-start/stop the plugin — no explicit plugin.start() /
plugin.stop() calls needed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from typing import AsyncGenerator

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flowcept import Flowcept
# Use whichever LLM provider has a key in the environment.
if os.getenv("ANTHROPIC_API_KEY"):
    from flowcept.agents.autogen.autogen_plugin import anthropic_chat as llm_chat

    LLM_MODEL = "claude-haiku-4-5-20251001"
else:
    from flowcept.agents.autogen.autogen_plugin import openai_chat as llm_chat

    LLM_MODEL = "gpt-4o-mini"
from flowcept.agents.autogen.autogen_plugin import run_team

try:
    from autogen_agentchat.agents import AssistantAgent
    from autogen_agentchat.conditions import MaxMessageTermination
    from autogen_agentchat.teams import RoundRobinGroupChat
    from autogen_core.models import ChatCompletionClient, CreateResult, RequestUsage, ModelInfo
except ImportError:
    print("ERROR: pip install autogen-agentchat", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Stub model client — canned counter responses, no API call needed
# ---------------------------------------------------------------------------

_STEPS = [1, 2, 3, 4, 5]
_RUNNING = 0
_STUB_RESPONSES = []
for _s in _STEPS:
    _RUNNING += _s
    _STUB_RESPONSES.append(
        f"assistant: increment({_s}) → running total = {_RUNNING}"
    )
_STUB_RESPONSES.append(
    f"critic: all 5 increments verified. Final value = {_RUNNING}. TERMINATE"
)

_stub_idx = 0


class _StubModelClient(ChatCompletionClient):
    """Returns canned counter responses without a real API call."""

    @property
    def model_info(self):
        return ModelInfo(vision=False, function_calling=False, json_output=False,
                         family="stub", structured_output=False)

    @property
    def capabilities(self):
        return ModelInfo(vision=False, function_calling=False, json_output=False)

    async def create(self, *_, **__) -> CreateResult:
        global _stub_idx
        content = _STUB_RESPONSES[_stub_idx % len(_STUB_RESPONSES)]
        _stub_idx += 1
        return CreateResult(
            content=content,
            usage=RequestUsage(prompt_tokens=20, completion_tokens=20),
            finish_reason="stop",
            cached=False,
        )

    async def create_stream(self, *_, **__) -> AsyncGenerator:
        yield await self.create()

    def actual_usage(self) -> RequestUsage:
        return RequestUsage(prompt_tokens=0, completion_tokens=0)

    def total_usage(self) -> RequestUsage:
        return RequestUsage(prompt_tokens=0, completion_tokens=0)

    def count_tokens(self, *_, **__) -> int:
        return 0

    def remaining_tokens(self, *_, **__) -> int:
        return 4096

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Agents and team
# ---------------------------------------------------------------------------

class AssistantCounterAgent(AssistantAgent):
    """Increments a counter and reports the running total."""

    def __init__(self):
        super().__init__(
            name="assistant",
            model_client=_StubModelClient(),
            system_message=(
                "You are a counter agent. Increment the counter by the given step "
                "and report the running total. When all 5 steps are done, end with TERMINATE."
            ),
        )


class CriticAgent(AssistantAgent):
    """Verifies each running total."""

    def __init__(self):
        super().__init__(
            name="critic",
            model_client=_StubModelClient(),
            system_message=(
                "You are a verifier. Check each running total and confirm it is correct. "
                "When TERMINATE is reached, echo it."
            ),
        )


# ---------------------------------------------------------------------------
# Driver — mirrors academy_example._run()
# ---------------------------------------------------------------------------

async def _run() -> None:
    assistant = AssistantCounterAgent()
    critic = CriticAgent()
    termination = MaxMessageTermination(max_messages=len(_STUB_RESPONSES) + 1)
    team = RoundRobinGroupChat(
        participants=[assistant, critic],
        termination_condition=termination,
    )

    task = "Increment a counter 5 times with step values 1, 2, 3, 4, 5 and report each running total."
    print(f"\n[example] Task: {task!r}\n", flush=True)

    # run_team() uses _ACTIVE_INTERCEPTOR — no explicit plugin handle needed,
    # mirroring how openai_chat() / anthropic_chat() work.
    result = await run_team(team, task, team_name="counter-team")

    # Parse final total — mirrors SummaryAgent.get_result()
    final_value = 0
    for msg in result.messages:
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            for token in content.split():
                try:
                    final_value = int(token.strip(".,"))
                except ValueError:
                    pass

    print("\n" + "=" * 60)
    print("TEAM CONVERSATION")
    print("=" * 60)
    for msg in result.messages:
        source = getattr(msg, "source", "?")
        content = getattr(msg, "content", "")
        print(f"\n[{source}]\n{content}")
    print(f"\nStop reason: {result.stop_reason}")

    # Interpret the result — mirrors SummaryAgent.interpret_result() @action.
    # llm_chat() fires record_llm_call() automatically.
    print("\n[example] Calling llm_chat() to interpret the counter result …", flush=True)
    interpretation = llm_chat(
        prompt=(
            f"A counter was incremented 5 times with values 1, 2, 3, 4, 5 "
            f"and reached a final value of {final_value}. "
            f"In exactly one sentence, explain what this arithmetic result represents."
        ),
        model=LLM_MODEL,
        system="You are a concise data analyst.",
        temperature=0.3,
        context={"agent": "counter-team", "call_type": "interpret_result"},
    )
    print(f"\n[example] LLM says: {interpretation}\n", flush=True)
    print(f"[example] Counter reached {final_value}  (expected 15 = 1+2+3+4+5)", flush=True)
    assert final_value == 15, f"Expected 15 but got {final_value}"
    print("[example] Assertion passed.", flush=True)


def main() -> None:
    with Flowcept():
        asyncio.run(_run())


if __name__ == "__main__":
    main()
