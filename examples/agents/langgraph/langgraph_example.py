"""
examples/agents/langgraph/langgraph_example.py
===============================================

Counter test mirroring the Academy example:

    [add_1] → [add_2] → [add_3] → [add_4] → [add_5] → [interpret]

Each node adds its step value to the running total.
The final node calls llm_chat() to interpret the result (15 = 1+2+3+4+5).

Run
---
    OPENAI_API_KEY=sk-... (or ANTHROPIC_API_KEY=sk-ant-...) python examples/agents/langgraph/langgraph_example.py

Plugin configuration
--------------------
Enable the LangGraph plugin in your settings.yaml:

    plugins:
      langgraph:
        enabled: true
        kind: langgraph
        workflow_name: "langgraph-counter-test"
        performance_tracking: true

Flowcept will auto-start/stop the plugin — no explicit plugin.start() /
plugin.stop() calls needed.  Access the running plugin via
flowcept.plugins["langgraph"] to retrieve the callback_handler.
"""
from __future__ import annotations

import os
import sys
from typing import TypedDict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flowcept import Flowcept
# Use whichever LLM provider has a key in the environment.
if os.getenv("ANTHROPIC_API_KEY"):
    from flowcept.agents.langgraph.langgraph_plugin import anthropic_chat as llm_chat

    LLM_MODEL = "claude-haiku-4-5-20251001"
else:
    from flowcept.agents.langgraph.langgraph_plugin import openai_chat as llm_chat

    LLM_MODEL = "gpt-4o-mini"

try:
    from langgraph.graph import StateGraph, END
except ImportError:
    print(
        "ERROR: LangGraph not installed.\n"
        "  pip install langgraph langchain-core",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Graph state
# ---------------------------------------------------------------------------

class CounterState(TypedDict):
    total: int
    steps: list[int]
    interpretation: str


# ---------------------------------------------------------------------------
# Graph nodes — each adds its step value to the running total
# ---------------------------------------------------------------------------

def _make_add_node(step: int):
    def node(state: CounterState) -> CounterState:
        new_total = state["total"] + step
        steps = list(state["steps"]) + [step]
        print(f"[node] increment({step}) → total = {new_total}", flush=True)
        return {"total": new_total, "steps": steps}
    node.__name__ = f"add_{step}"
    return node


def interpret_node(state: CounterState) -> CounterState:
    """Call the LLM to interpret the final counter value."""
    total = state["total"]
    steps = state["steps"]
    steps_str = "+".join(str(s) for s in steps)
    interpretation = llm_chat(
        prompt=(
            f"A counter was incremented {len(steps)} times with values {steps_str} "
            f"and reached a final value of {total}. "
            f"In exactly one sentence, explain what this arithmetic result represents."
        ),
        model=LLM_MODEL,
        system="You are a concise data analyst.",
        temperature=0.3,
        context={"node": "interpret", "call_type": "interpret_result"},
    )
    print(f"[node] LLM says: {interpretation}", flush=True)
    return {"interpretation": interpretation}


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def build_graph():
    builder = StateGraph(CounterState)

    for step in range(1, 6):
        builder.add_node(f"add_{step}", _make_add_node(step))
    builder.add_node("interpret", interpret_node)

    builder.set_entry_point("add_1")
    for step in range(1, 5):
        builder.add_edge(f"add_{step}", f"add_{step + 1}")
    builder.add_edge("add_5", "interpret")
    builder.add_edge("interpret", END)

    return builder.compile()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    graph = build_graph()

    print("\n[example] Running counter graph …\n", flush=True)

    initial_state: CounterState = {
        "total":          0,
        "steps":          [],
        "interpretation": "",
    }

    with Flowcept() as flowcept:
        plugin = flowcept.plugins.get("langgraph")
        if plugin is None:
            raise RuntimeError(
                "LangGraph plugin is not enabled. Set 'plugins.langgraph.enabled: true' in settings.yaml."
            )
        final_state = graph.invoke(
            initial_state,
            config={"callbacks": [plugin.callback_handler]},
        )

    print("\n" + "=" * 60)
    print("GRAPH OUTPUT")
    print("=" * 60)
    steps_str = "+".join(str(s) for s in final_state["steps"])
    print(f"\nSteps    : {steps_str} = {final_state['total']}  (expected 15)")
    print(f"\nLLM says : {final_state['interpretation']}")
    assert final_state["total"] == 15, f"Expected 15 but got {final_state['total']}"
    print("\n[example] Assertion passed.", flush=True)


if __name__ == "__main__":
    main()
