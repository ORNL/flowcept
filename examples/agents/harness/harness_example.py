"""Example: capture an AI coding-harness session as Flowcept PROV-AGENT provenance.

The harness plugins (flowcept.agents.harness and the per-harness plugin
modules) capture what an agentic coding session actually did — prompts, turns,
tool calls, subagents — into a JSONL buffer Flowcept reads natively.

Most captures need no code at all:

* Claude Code           — install the plugin in ``plugins/flowcept`` or run
                          ``flowcept-harness install``
* Codex / Gemini / ...  — point the harness's hook at
                          ``flowcept-harness hook --harness codex --profile codex``
* OpenTelemetry GenAI   — ``flowcept.agents.otel.otel_plugin.FlowceptSpanExporter``
* OpenAI Agents SDK     — ``flowcept.agents.openai_agents.openai_agents_plugin.install()``
* LangChain / LangGraph — ``flowcept.agents.langchain.langchain_plugin.FlowceptCallbackHandler``
* Claude Agent SDK      — ``flowcept.agents.claude_agent_sdk.claude_agent_sdk_plugin.trace_query``

This example shows the one case that does need code: an agent you wrote
yourself, driven through :class:`SessionTracer`. Afterwards, inspect the
capture with ``flowcept-harness sessions`` / ``show`` / ``report``.
"""

from flowcept.agents.harness import SessionTracer


def main():
    """Trace a tiny hand-rolled agent session."""
    with SessionTracer("example_agent", model="claude-opus-5") as tracer:
        tracer.prompt("summarize the repository")

        with tracer.tool("read_file", {"path": "README.md"}) as call:
            call.result({"content": "# Flowcept ..."})

        with tracer.tool("run_tests", {"suite": "unit"}) as call:
            call.result({"passed": 42, "failed": 0})

        tracer.turn_end(
            "The repository is Flowcept; all 42 unit tests pass.",
            usage={"input_tokens": 900, "output_tokens": 120},
        )

    print("Captured. Inspect with:")
    print("  flowcept-harness sessions")
    print("  flowcept-harness show")
    print("  flowcept-harness report")


if __name__ == "__main__":
    main()
