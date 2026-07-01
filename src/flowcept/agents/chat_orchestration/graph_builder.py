"""LangGraph agent graph construction for the chat orchestrator."""

from __future__ import annotations

import json
from typing import Optional

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph

from flowcept.commons.utils import sanitize_json_like
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.configs import AGENT_CHAT_MAX_TOOL_RESULT_CHARS, INSTRUMENTATION_ENABLED

_MAX_TOOL_RESULT_CHARS = AGENT_CHAT_MAX_TOOL_RESULT_CHARS

# Module-level saver — persists across requests keyed by thread_id.
memory = MemorySaver()


def _build_graph(llm, tools, agent_id: Optional[str] = None, require_first_tool: bool = False):
    """Build a LangGraph agent + tools graph compiled with the module-level MemorySaver.

    When *require_first_tool* is True the first agent node uses ``tool_choice="required"``
    so the LLM is forced to call at least one tool before producing a final answer.
    Which tool it calls is determined by the system prompt rules — no keyword-based
    routing is applied here.
    """
    bound = llm.bind_tools(tools)
    first_bound = llm.bind_tools(tools, tool_choice="required") if require_first_tool else bound
    tools_by_name = {t.name: t for t in tools}

    def _needs_first_tool(state: MessagesState) -> bool:
        return require_first_tool and not any(isinstance(message, ToolMessage) for message in state["messages"])

    if INSTRUMENTATION_ENABLED and agent_id is not None:
        from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM
        from flowcept.instrumentation.task_capture import FlowceptTask

        instrumented_llm = FlowceptLLM(bound, agent_id=agent_id, return_response_object=True)

        def call_model(state: MessagesState):
            """Agent node: invoke the LLM with current messages (instrumented)."""
            active_llm = (
                FlowceptLLM(first_bound, agent_id=agent_id, return_response_object=True)
                if _needs_first_tool(state)
                else instrumented_llm
            )
            return {"messages": [active_llm.invoke(state["messages"])]}

        def call_tools(state: MessagesState):
            """Tools node: execute all pending tool calls with provenance capture."""
            last = state["messages"][-1]
            tool_msgs = []
            for tc in getattr(last, "tool_calls", []):
                name = tc["name"]
                args = tc.get("args") or {}
                call_id = tc.get("id") or name
                tool_fn = tools_by_name.get(name)
                with FlowceptTask(
                    activity_id=name,
                    subtype=PROV_AGENT.AGENT_TOOL,
                    used=sanitize_json_like(args, mongo_safe_keys=True),
                    agent_id=agent_id,
                ) as task:
                    output = (
                        tool_fn.invoke(args) if tool_fn is not None else json.dumps({"error": f"Unknown tool {name}"})
                    )
                    task.end(generated={"output": output[:500] if isinstance(output, str) else output})
                if isinstance(output, str) and len(output) > _MAX_TOOL_RESULT_CHARS:
                    output = output[:_MAX_TOOL_RESULT_CHARS] + f"... [truncated, {len(output)} chars total]"
                tool_msgs.append(ToolMessage(content=output, tool_call_id=call_id, name=name))
            return {"messages": tool_msgs}

    else:

        def call_model(state: MessagesState):
            """Agent node: invoke the LLM with current messages."""
            response = (first_bound if _needs_first_tool(state) else bound).invoke(state["messages"])
            return {"messages": [response]}

        def call_tools(state: MessagesState):
            """Tools node: execute all pending tool calls and return ToolMessages."""
            last = state["messages"][-1]
            tool_msgs = []
            for tc in getattr(last, "tool_calls", []):
                name = tc["name"]
                args = tc.get("args") or {}
                call_id = tc.get("id") or name
                tool_fn = tools_by_name.get(name)
                output = tool_fn.invoke(args) if tool_fn is not None else json.dumps({"error": f"Unknown tool {name}"})
                if isinstance(output, str) and len(output) > _MAX_TOOL_RESULT_CHARS:
                    output = output[:_MAX_TOOL_RESULT_CHARS] + f"... [truncated, {len(output)} chars total]"
                tool_msgs.append(ToolMessage(content=output, tool_call_id=call_id, name=name))
            return {"messages": tool_msgs}

    def should_continue(state: MessagesState):
        """Route to tools if the last AI message has tool calls; otherwise end."""
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", call_tools)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue)
    graph.add_edge("tools", "agent")
    return graph.compile(checkpointer=memory)
