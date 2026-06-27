"""LLM chat orchestration for the webservice: LangGraph + MemorySaver tool-calling loop."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.errors import GraphRecursionError

from flowcept.agents.chat_orchestration.graph_builder import _build_graph, memory as _memory
from flowcept.agents.data_query_tools.base_query_tools import BaseQueryTools
from flowcept.agents.chat_orchestration.tool_registry import _build_langchain_tools, _format_error
from flowcept.agents.prompts.chat_prompts import build_chat_system_prompt
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_CHAT_MAX_TOOL_ITERATIONS, INSTRUMENTATION_ENABLED

MAX_TOOL_ITERATIONS = AGENT_CHAT_MAX_TOOL_ITERATIONS
CHAT_WORKFLOW_NAME = "Flowcept LangGraph Chat"

# Matches LLM text responses that are Python code instead of natural language.
# Catches: single-line result = "...", AND multi-line code blocks containing df[ with result assignments.
_CODE_RESPONSE_RE = re.compile(
    r"^\s*result\s*=\s*[\"'][^\"']{0,500}[\"'][\s;]*$"  # result = "string"
    r"|^\s*result\s*=\s*df\b"  # result = df[...]
    r"|.*\bdf\s*\[.*\bresult\s*="  # multi-line code with df[ before result =
    r"|^\s*\w+\s*=\s*\[.*\bdf\.columns\b",  # any_var = [...df.columns...]
    re.DOTALL,
)


def _prepare_input_messages(
    messages: List[Dict[str, str]],
    context: Optional[Dict[str, Any]],
    thread_id: Optional[str],
) -> List:
    """Convert client messages to LangChain message objects.

    When a stateful thread already has a checkpoint, only the new user messages
    are returned (server owns history via MemorySaver).  For new threads and
    stateless calls the full message list is returned with the system prompt
    prepended.
    """
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    is_new_thread = config is None or _memory.get(config) is None

    lc_messages = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        lc_messages.append(AIMessage(content=content) if role == "assistant" else HumanMessage(content=content))

    if is_new_thread:
        lc_messages = [SystemMessage(content=build_chat_system_prompt(context))] + lc_messages

    return lc_messages


def run_chat(
    llm,
    messages: List[Dict[str, str]],
    context: Optional[Dict[str, Any]] = None,
    allow_dashboard_edit: bool = False,
    thread_id: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Run one chat turn as a generator of events backed by LangGraph + MemorySaver.

    Yields dict events: ``{"event": "tool_call"|"tool_result"|"card"|"token"|"done"|"error", ...}``.

    When *thread_id* is ``None`` the call is stateless (client manages full history in
    *messages*).  When *thread_id* is provided the server owns history: pass only the
    new message(s) in *messages* on follow-up turns.

    Parameters
    ----------
    llm : Any
        A langchain chat model (from ``build_llm_model``).
    messages : list of dict
        ``[{"role": "user"|"assistant", "content": "..."}]``.
        Full history when *thread_id* is ``None``; only new messages otherwise.
    context : dict, optional
        UI context injected into the system prompt and chart tool.
    allow_dashboard_edit : bool, optional
        Whether dashboard-modifying tools are bound.
    thread_id : str, optional
        Stable ID that keys server-side conversation memory.
    """
    logger = FlowceptLogger()
    context = BaseQueryTools.enrich_context(context)
    tools = _build_langchain_tools(context, allow_dashboard_edit)

    effective_thread_id = thread_id if thread_id is not None else str(uuid.uuid4())

    agent_id: Optional[str] = None
    if INSTRUMENTATION_ENABLED:
        from flowcept.flowceptor.consumers.agent.base_agent_context_manager import BaseAgentContextManager

        agent_id = BaseAgentContextManager.agent_id or effective_thread_id

    try:
        llm.bind_tools(tools)
    except (NotImplementedError, AttributeError):
        logger.warning("Chat LLM does not support tool binding; answering without tools.")
        from langchain_core.messages import SystemMessage as _SM

        lc = [_SM(content=build_chat_system_prompt(context))] + [
            AIMessage(content=m.get("content", ""))
            if m.get("role") == "assistant"
            else HumanMessage(content=m.get("content", ""))
            for m in messages
        ]
        try:
            response = llm.invoke(lc)
            yield {"event": "token", "data": getattr(response, "content", str(response))}
        except Exception as exc:
            logger.exception(exc)
            yield {"event": "error", "data": str(exc)}
        yield {"event": "done"}
        return

    config = {
        "configurable": {"thread_id": effective_thread_id},
        "recursion_limit": MAX_TOOL_ITERATIONS * 2 + 2,
    }

    graph = _build_graph(
        llm,
        tools,
        agent_id=agent_id,
        require_first_tool=(context or {}).get("tool_context", "db") in {"db", "df"},
    )
    lc_messages = _prepare_input_messages(messages, context, thread_id)

    # Each LangGraph execution gets its own Flowcept workflow so all AI model
    # invocations and tool calls within this call share a single workflow_id.
    from flowcept.flowcept_api.flowcept_controller import Flowcept as _FC

    with _FC(
        workflow_name=CHAT_WORKFLOW_NAME,
        start_persistence=True,
        save_workflow=True,
        agent_name="FlowceptAgent",
    ):
        accumulated_tool_results: List[str] = []
        try:
            for chunk in graph.stream({"messages": lc_messages}, config=config, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    msgs = node_output.get("messages", [])
                    if node_name == "agent":
                        last = msgs[-1] if msgs else None
                        if last is None:
                            continue
                        tool_calls = getattr(last, "tool_calls", None) or []
                        if tool_calls:
                            for tc in tool_calls:
                                yield {"event": "tool_call", "data": {"name": tc["name"], "args": tc.get("args", {})}}
                        else:
                            content = getattr(last, "content", "")
                            if _CODE_RESPONSE_RE.match(content.strip()):
                                user_query = messages[-1].get("content", "") if messages else ""
                                tool_data = "\n".join(accumulated_tool_results[-3:]) if accumulated_tool_results else ""
                                try:
                                    rephrase = llm.invoke(
                                        [
                                            HumanMessage(
                                                content=(
                                                    f"The user asked: {user_query!r}\n"
                                                    + (
                                                        f"Tool results already retrieved:\n{tool_data}\n"
                                                        if tool_data
                                                        else ""
                                                    )
                                                    + f"The LLM produced Python code instead of an answer: {content}\n"
                                                    "Write a single plain English sentence answering the "
                                                    "user's question using the tool results above. "
                                                    "If the data is not available, say so specifically"
                                                    " (mention the metric asked about). "
                                                    "Do not use Python code or variable assignments."
                                                )
                                            )
                                        ]
                                    )
                                    content = getattr(rephrase, "content", content) or content
                                except Exception:
                                    pass
                            yield {"event": "token", "data": content}
                            yield {"event": "done"}
                    elif node_name == "tools":
                        for tm in msgs:
                            name = getattr(tm, "name", "")
                            accumulated_tool_results.append(f"[{name}]: {tm.content[:2000]}")
                            summary: Dict[str, Any] = {"name": name}
                            try:
                                parsed = json.loads(tm.content)
                                summary["code"] = parsed.get("code")
                                summary["tool_name"] = parsed.get("tool_name")
                                if name == "make_chart" and isinstance(parsed.get("result"), dict):
                                    yield {"event": "card", "data": parsed["result"]}
                                if name == "highlight_lineage" and isinstance(parsed.get("result"), dict):
                                    yield {"event": "ui:highlight", "data": parsed["result"]}
                            except Exception:
                                pass
                            yield {"event": "tool_result", "data": summary}
        except GraphRecursionError:
            logger.warning(
                f"LLM hit the tool-call recursion limit ({MAX_TOOL_ITERATIONS} iterations) "
                "without producing a final answer. Synthesizing from accumulated tool results."
            )
            if accumulated_tool_results:
                summary_prompt = (
                    "The following tool results were retrieved. "
                    "Write a concise final answer to the user's question based solely on this data. "
                    "Do not call any tools.\n\n" + "\n\n".join(accumulated_tool_results)
                )
                try:
                    response = llm.invoke([HumanMessage(content=summary_prompt)])
                    content = getattr(response, "content", None) or str(response)
                    if content:
                        yield {"event": "token", "data": content}
                    else:
                        yield {"event": "token", "data": "\n\n".join(accumulated_tool_results[:3])}
                except Exception as fallback_exc:
                    logger.exception(fallback_exc)
                    yield {"event": "token", "data": "\n\n".join(accumulated_tool_results[:3])}
            else:
                yield {"event": "error", "data": "Reached tool call limit without retrieving any data."}
            yield {"event": "done"}
        except Exception as e:
            logger.exception(e)
            yield {"event": "error", "data": _format_error(e)}
