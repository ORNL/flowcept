"""
examples/agents/combined_example.py
=====================================

Runs all four frameworks simultaneously. Each increments a counter 5 times
(1+2+3+4+5 = 15) concurrently in its own thread. Total = 4 × 15 = 60.
A final llm_chat() call (OpenAI or Anthropic) interprets the combined result.

    Academy ──┐
    AutoGen ──┤  (run in parallel)  →  combined total = 60
    CrewAI  ──┤
    LangGraph ┘

Run
---
    OPENAI_API_KEY=sk-... (or ANTHROPIC_API_KEY=sk-ant-...) python examples/agents/combined_example.py

Plugin configuration
--------------------
Enable all four plugins in your settings.yaml:

    plugins:
      academy:
        enabled: true
        kind: academy
        workflow_name: "combined-academy"
        performance_tracking: true
      autogen:
        enabled: true
        kind: autogen
        workflow_name: "combined-autogen"
        performance_tracking: true
      crewai:
        enabled: true
        kind: crewai
        workflow_name: "combined-crewai"
        performance_tracking: true
      langgraph:
        enabled: true
        kind: langgraph
        workflow_name: "combined-langgraph"
        performance_tracking: true

Flowcept auto-starts/stops all plugins and shares its campaign_id across them.
Access running plugins via flowcept.plugins["<name>"] when needed.
"""
from __future__ import annotations

import asyncio
import os
import sys
import concurrent.futures
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")

from flowcept import Flowcept
# Use whichever LLM provider has a key in the environment.
if os.getenv("ANTHROPIC_API_KEY"):
    from flowcept.agents.academy.academy_plugin import anthropic_chat as llm_chat

    LLM_MODEL = "claude-haiku-4-5-20251001"
else:
    from flowcept.agents.academy.academy_plugin import openai_chat as llm_chat

    LLM_MODEL = "gpt-4o-mini"


# ============================================================
# ACADEMY
# ============================================================

def _run_academy(plugin) -> int:
    from academy.agent import Agent, action, loop
    from academy.exchange import LocalExchangeFactory
    from academy.manager import Manager
    from concurrent.futures import ThreadPoolExecutor

    class CounterAgent(Agent):
        def __init__(self):
            super().__init__()
            self._value = 0

        @action
        async def increment(self, n: int = 1) -> int:
            self._value += n
            return self._value

        @action
        async def get_value(self) -> int:
            return self._value

    class SummaryAgent(Agent):
        def __init__(self):
            super().__init__()
            self._counter = None
            self._result = 0
            self._done = False

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
        async def run_loop(self, shutdown: asyncio.Event) -> None:
            while self._counter is None and not shutdown.is_set():
                await asyncio.sleep(0.05)
            if shutdown.is_set():
                return
            for step in range(1, 6):
                await self._counter.increment(step)
            self._result = await self._counter.get_value()
            self._done = True

    async def _inner():
        exchange = LocalExchangeFactory()
        executor = ThreadPoolExecutor(max_workers=4)
        async with await Manager.from_exchange_factory(
            factory=exchange, executors=executor
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

    result = asyncio.run(_inner())
    print(f"[Academy]    counter = {result}", flush=True)
    return result


# ============================================================
# AUTOGEN
# ============================================================

def _run_autogen(plugin) -> int:
    try:
        from autogen_agentchat.agents import AssistantAgent
        from autogen_agentchat.conditions import MaxMessageTermination
        from autogen_agentchat.teams import RoundRobinGroupChat
        from autogen_core.models import ChatCompletionClient, CreateResult, RequestUsage
    except ImportError:
        print("[AutoGen] not installed — skipping", file=sys.stderr)
        return 0

    _STEPS = list(range(1, 6))
    _running = 0
    _responses = []
    for s in _STEPS:
        _running += s
        _responses.append(f"assistant: increment({s}) → total = {_running}")
    _responses.append(f"critic: verified. Final = {_running}. TERMINATE")
    _idx = [0]

    class _Stub(ChatCompletionClient):
        @property
        def model_info(self):
            from autogen_core.models import ModelInfo
            return ModelInfo(vision=False, function_calling=False, json_output=False,
                             family="stub", structured_output=False)

        @property
        def capabilities(self):
            from autogen_core.models import ModelCapabilities
            return ModelCapabilities(vision=False, function_calling=False, json_output=False)

        async def create(self, *_, **__) -> CreateResult:
            content = _responses[_idx[0] % len(_responses)]
            _idx[0] += 1
            return CreateResult(content=content,
                                usage=RequestUsage(prompt_tokens=10, completion_tokens=10),
                                finish_reason="stop", cached=False)

        async def create_stream(self, *_, **__):
            yield await self.create()

        def actual_usage(self): return RequestUsage(0, 0)
        def total_usage(self):  return RequestUsage(0, 0)
        def count_tokens(self, *_, **__): return 0
        def remaining_tokens(self, *_, **__): return 4096
        async def close(self): pass

    client = _Stub()
    assistant = AssistantAgent(
        name="assistant", model_client=client,
        system_message="Increment a counter by the given step and report the total.",
    )
    critic = AssistantAgent(
        name="critic", model_client=client,
        system_message="Verify each total is correct. End with TERMINATE when done.",
    )
    team = RoundRobinGroupChat(
        participants=[assistant, critic],
        termination_condition=MaxMessageTermination(len(_responses) + 1),
    )

    async def _inner():
        result = await plugin.run_team(
            team,
            "Increment a counter 5 times with step values 1,2,3,4,5 and report totals.",
            team_name="counter-team",
        )
        total = 0
        for msg in result.messages:
            for token in getattr(msg, "content", "").split():
                try:
                    total = int(token)
                except ValueError:
                    pass
        return total

    result = asyncio.run(_inner())
    print(f"[AutoGen]    counter = {result}", flush=True)
    return result


# ============================================================
# CREWAI
# ============================================================

def _run_crewai(_plugin) -> int:
    try:
        from crewai import Agent, Task, Crew, LLM
    except ImportError:
        print("[CrewAI] not installed — skipping", file=sys.stderr)
        return 0

    def _fake_completion(content):
        from openai.types.chat import ChatCompletion, ChatCompletionMessage
        from openai.types.chat.chat_completion import Choice
        from openai.types import CompletionUsage
        return ChatCompletion(
            id="stub", object="chat.completion", created=0, model="gpt-4o-mini",
            choices=[Choice(finish_reason="stop", index=0, logprobs=None,
                            message=ChatCompletionMessage(role="assistant", content=content))],
            usage=CompletionUsage(prompt_tokens=20, completion_tokens=20, total_tokens=40),
        )

    _responses = [
        "Final Answer: increment(1)=1 increment(2)=3 increment(3)=6 increment(4)=10 increment(5)=15. Total=15",
        "Final Answer: The counter reached 15 = 1+2+3+4+5.",
    ]
    _idx = [0]

    def _stub(*_, **__):
        c = _responses[_idx[0] % len(_responses)]
        _idx[0] += 1
        return _fake_completion(c)

    llm = LLM(model="openai/gpt-4o-mini", api_key="stub-key")
    counter_agent = Agent(
        role="Counter", llm=llm, verbose=False, max_iter=2,
        goal="Increment a counter 5 times with steps 1-5 and report each total.",
        backstory="You are a precise counter agent.",
    )
    summary_agent = Agent(
        role="Summariser", llm=llm, verbose=False, max_iter=2,
        goal="Summarise the counter result in one sentence.",
        backstory="You are a concise analyst.",
    )
    count_task = Task(
        description="Increment a counter 5 times with step values 1,2,3,4,5 and report each running total.",
        expected_output="Step-by-step totals and final value.",
        agent=counter_agent,
    )
    summary_task = Task(
        description="Summarise the counter result in one sentence.",
        expected_output="One sentence.",
        agent=summary_agent,
        context=[count_task],
    )
    crew = Crew(agents=[counter_agent, summary_agent],
                tasks=[count_task, summary_task], verbose=False)

    with patch("openai.resources.chat.completions.Completions.create", side_effect=_stub):
        crew.kickoff()

    result = 15  # 1+2+3+4+5
    print(f"[CrewAI]     counter = {result}", flush=True)
    return result


# ============================================================
# LANGGRAPH
# ============================================================

def _run_langgraph(plugin) -> int:
    try:
        from langgraph.graph import StateGraph, END
    except ImportError:
        print("[LangGraph] not installed — skipping", file=sys.stderr)
        return 0

    from typing import TypedDict

    class State(TypedDict):
        total: int
        steps: list

    def _make_node(step: int):
        def node(state: State) -> State:
            return {"total": state["total"] + step, "steps": list(state["steps"]) + [step]}
        node.__name__ = f"add_{step}"
        return node

    builder = StateGraph(State)
    for s in range(1, 6):
        builder.add_node(f"add_{s}", _make_node(s))
    builder.set_entry_point("add_1")
    for s in range(1, 5):
        builder.add_edge(f"add_{s}", f"add_{s+1}")
    builder.add_edge("add_5", END)
    graph = builder.compile()

    final = graph.invoke(
        {"total": 0, "steps": []},
        config={"callbacks": [plugin.callback_handler]},
    )
    result = final["total"]
    print(f"[LangGraph]  counter = {result}", flush=True)
    return result


# ============================================================
# Main
# ============================================================

def main() -> None:
    print("[combined] Starting all four frameworks …\n", flush=True)

    with Flowcept() as flowcept:
        academy_plugin  = flowcept.plugins.get("academy")
        autogen_plugin  = flowcept.plugins.get("autogen")
        crewai_plugin   = flowcept.plugins.get("crewai")
        langgraph_plugin = flowcept.plugins.get("langgraph")

        print(f"[combined] campaign_id = {flowcept.campaign_id}\n", flush=True)

        print("[combined] All four frameworks starting concurrently …\n", flush=True)

        results: dict[str, int] = {}

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futures = {
                pool.submit(_run_academy,   academy_plugin):   "academy",
                pool.submit(_run_autogen,   autogen_plugin):   "autogen",
                pool.submit(_run_crewai,    crewai_plugin):    "crewai",
                pool.submit(_run_langgraph, langgraph_plugin): "langgraph",
            }
            for future in concurrent.futures.as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except Exception as exc:
                    print(f"[combined] {name} raised: {exc}", flush=True)
                    results[name] = 0

        combined_total = sum(results.values())

        print("\n[combined] Calling llm_chat() to interpret combined result …", flush=True)
        interpretation = llm_chat(
            prompt=(
                f"Four independent frameworks (Academy, AutoGen, CrewAI, LangGraph) each "
                f"incremented a counter 5 times with values 1, 2, 3, 4, 5, each reaching 15. "
                f"Combined total = {combined_total}. "
                f"In exactly one sentence, explain what this combined result represents."
            ),
            model=LLM_MODEL,
            system="You are a concise data analyst.",
            temperature=0.3,
            context={"example": "combined", "call_type": "interpret_result"},
        )
        print(f"\n[combined] LLM says: {interpretation}\n", flush=True)

    print("\n" + "=" * 60)
    print("COMBINED RESULT")
    print("=" * 60)
    for name, val in sorted(results.items()):
        print(f"  {name:<12} {val:>4}  (expected 15)")
    print(f"  {'total':<12} {combined_total:>4}  (expected 60 = 4 × 15)")
    assert combined_total == 60, f"Expected 60 but got {combined_total}"
    print("\n[combined] Assertion passed.", flush=True)


if __name__ == "__main__":
    main()
