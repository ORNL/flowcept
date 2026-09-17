"""
Academy example
===============

Two Academy agents increment a counter five times (1+2+3+4+5 = 15), then an
llm_chat() call (OpenAI or Anthropic) interprets the final value — mirroring the AutoGen / CrewAI /
LangGraph examples.

Run
---
    OPENAI_API_KEY=sk-... (or ANTHROPIC_API_KEY=sk-ant-...) python examples/agents/academy/academy_example.py

Plugin configuration
--------------------
Enable the Academy plugin in your settings.yaml:

    plugins:
      academy:
        enabled: true
        kind: academy
        workflow_name: "academy-counter"
        performance_tracking: true

Flowcept will auto-start/stop the plugin — no explicit plugin.start() /
plugin.stop() calls needed.
"""
from __future__ import annotations

import asyncio
import os
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from academy.agent import Agent, action, loop
from academy.exchange import LocalExchangeFactory
from academy.manager import Manager

from flowcept import Flowcept
# Use whichever LLM provider has a key in the environment.
if os.getenv("ANTHROPIC_API_KEY"):
    from flowcept.agents.academy.academy_plugin import anthropic_chat as llm_chat

    LLM_MODEL = "claude-haiku-4-5-20251001"
else:
    from flowcept.agents.academy.academy_plugin import openai_chat as llm_chat

    LLM_MODEL = "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Agent definitions
# ---------------------------------------------------------------------------


class CounterAgent(Agent):
    """Simple integer counter."""

    def __init__(self) -> None:
        super().__init__()
        self._value: int = 0

    @action
    async def increment(self, n: int = 1) -> int:
        self._value += n
        return self._value

    @action
    async def get_value(self) -> int:
        return self._value


class SummaryAgent(Agent):
    """Increments the CounterAgent five times and records the final value."""

    def __init__(self) -> None:
        super().__init__()
        self._counter = None
        self._result: int = 0
        self._done: bool = False

    @action
    async def set_counter(self, counter) -> None:
        self._counter = counter

    @action
    async def get_result(self) -> int:
        return self._result

    @action
    async def is_done(self) -> bool:
        return self._done

    @loop
    async def summary_loop(self, shutdown: asyncio.Event) -> None:
        while self._counter is None and not shutdown.is_set():
            await asyncio.sleep(0.05)
        if shutdown.is_set():
            return

        print("[SummaryAgent] Starting counter cycle …", flush=True)
        for step in range(1, 6):
            value = await self._counter.increment(step)
            print(f"[SummaryAgent]   increment({step}) → counter={value}", flush=True)

        self._result = await self._counter.get_value()
        print(f"[SummaryAgent] Final counter value: {self._result}", flush=True)
        self._done = True


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def _run() -> int:
    exchange = LocalExchangeFactory()
    executor = ThreadPoolExecutor(max_workers=4)

    async with await Manager.from_exchange_factory(
        factory=exchange,
        executors=executor,
    ) as manager:
        counter = await manager.launch(CounterAgent)
        await counter.ping()

        summary = await manager.launch(SummaryAgent)
        await summary.ping()

        await summary.set_counter(counter)

        for _ in range(60):
            await asyncio.sleep(0.5)
            if await summary.is_done():
                break

        return await summary.get_result()


def main() -> None:
    import logging

    logging.basicConfig(level=logging.INFO)

    with Flowcept():
        result = asyncio.run(_run())

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(f"\nCounter reached {result}  (expected 15 = 1+2+3+4+5)", flush=True)
    assert result == 15, f"Expected 15 but got {result}"

    print("\n[example] Calling llm_chat() to interpret the counter result …", flush=True)
    interpretation = llm_chat(
        prompt=(
            f"A counter was incremented 5 times with values 1, 2, 3, 4, 5 "
            f"and reached a final value of {result}. "
            f"In exactly one sentence, explain what this arithmetic result represents."
        ),
        model=LLM_MODEL,
        system="You are a concise data analyst.",
        temperature=0.3,
        context={"agent": "SummaryAgent", "call_type": "interpret_result"},
    )
    print(f"\n[example] LLM says: {interpretation}\n", flush=True)
    print("[example] Assertion passed.", flush=True)


if __name__ == "__main__":
    main()
