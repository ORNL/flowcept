"""LLM chat orchestration for the webservice: LangGraph + MemorySaver tool-calling loop."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph

from flowcept.agents.prompts.chat_prompts import CHAT_SYSTEM_PROMPT
from flowcept.agents.data_query_tools import db_query_tools as prov_tools
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_CHAT_MAX_TOOL_ITERATIONS

MAX_TOOL_ITERATIONS = AGENT_CHAT_MAX_TOOL_ITERATIONS

# Module-level saver — persists across requests keyed by thread_id.
_memory = MemorySaver()


def _build_langchain_tools(context: Optional[Dict[str, Any]], allow_dashboard_edit: bool):
    """Wrap the shared prov tool core as langchain tools (results JSON-encoded for the LLM)."""
    from langchain_core.tools import tool

    def _run(func, **kwargs) -> str:
        result = func(**kwargs)
        payload = result.model_dump() if hasattr(result, "model_dump") else result
        return json.dumps(payload, default=str)

    def _coerce_projection(p: Any) -> Optional[List[str]]:
        """Accept a list of field names or a Mongo projection dict {field: 1}."""
        if p is None:
            return None
        if isinstance(p, dict):
            return [k for k, v in p.items() if v]
        return list(p)

    def _coerce_sort(s: Any) -> Optional[List[Dict[str, Any]]]:
        """Accept [{field, order}] or a Mongo sort dict {field: -1}."""
        if s is None:
            return None
        if isinstance(s, dict):
            return [{"field": k, "order": v} for k, v in s.items()]
        return list(s)

    @tool
    def query_tasks(
        filter: Optional[Dict[str, Any]] = None,
        projection: Optional[Any] = None,
        limit: int = 100,
        sort: Optional[Any] = None,
    ) -> str:
        """Query task provenance records with a Mongo-style filter.

        projection: list of field names, or a Mongo projection dict {"field": 1}.
        sort: list of {"field": "...", "order": 1|-1}, or a Mongo sort dict {"field": -1}.
        """
        return _run(
            prov_tools.query_tasks,
            filter=filter,
            projection=_coerce_projection(projection),
            limit=limit,
            sort=_coerce_sort(sort),
        )

    @tool
    def query_workflows(filter: Optional[Dict[str, Any]] = None, limit: int = 100) -> str:
        """Query workflow provenance records with a Mongo-style filter."""
        return _run(prov_tools.query_workflows, filter=filter, limit=limit)

    @tool
    def get_task_summary(filter: Optional[Dict[str, Any]] = None) -> str:
        """Summarize tasks: status counts, per-activity durations, and time range."""
        return _run(prov_tools.get_task_summary, filter=filter)

    @tool
    def list_campaigns() -> str:
        """List derived campaign summaries (campaigns group workflows and tasks)."""
        return _run(prov_tools.list_campaigns)

    @tool
    def list_agents() -> str:
        """List derived agent summaries (agents observed in task provenance)."""
        return _run(prov_tools.list_agents)

    @tool
    def make_chart(card_spec: Dict[str, Any]) -> str:
        """Build a chart from a declarative dashboard card spec; the UI renders the result."""
        return _run(prov_tools.make_chart, card_spec=card_spec, context=context)

    @tool
    def highlight_lineage(
        task_ids: Optional[Any] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Highlight the full provenance lineage (ancestors + descendants) of tasks in the Dataflow graph.

        Pass `task_ids` as a list of task ID strings, or a single task ID string.
        Or use `filter` to find the seed tasks first.
        The UI will dim all other nodes and visually trace the lineage chain.
        Always pass a workflow_id in the filter when on a workflow page.
        """
        wf_id = (context or {}).get("workflow_id")
        ids: Optional[List[str]] = None
        if task_ids is not None:
            ids = [task_ids] if isinstance(task_ids, str) else list(task_ids)
        return _run(prov_tools.highlight_lineage, task_ids=ids, filter=filter, workflow_id=wf_id)

    tools = [query_tasks, query_workflows, get_task_summary, list_campaigns, list_agents, make_chart, highlight_lineage]

    if allow_dashboard_edit:

        @tool
        def get_dashboard(dashboard_id: str) -> str:
            """Get a stored dashboard spec by id."""
            return _run(prov_tools.get_dashboard, dashboard_id=dashboard_id)

        @tool
        def update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> str:
            """Replace a stored dashboard spec with a complete revised spec."""
            return _run(prov_tools.update_dashboard, dashboard_id=dashboard_id, spec=spec)

        tools += [get_dashboard, update_dashboard]
    return tools


def _build_graph(llm, tools):
    """Build a LangGraph agent + tools graph compiled with the module-level MemorySaver."""
    bound = llm.bind_tools(tools)
    tools_by_name = {t.name: t for t in tools}

    def call_model(state: MessagesState):
        """Agent node: invoke the LLM with current messages."""
        return {"messages": [bound.invoke(state["messages"])]}

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
    return graph.compile(checkpointer=_memory)


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
        system = CHAT_SYSTEM_PROMPT
        if context:
            system += f"\nCurrent user context (scope queries with it): {json.dumps(context)}"
        lc_messages = [SystemMessage(content=system)] + lc_messages

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
    tools = _build_langchain_tools(context, allow_dashboard_edit)

    try:
        llm.bind_tools(tools)
    except (NotImplementedError, AttributeError):
        logger.warning("Chat LLM does not support tool binding; answering without tools.")
        from langchain_core.messages import SystemMessage as _SM

        system = CHAT_SYSTEM_PROMPT
        if context:
            system += f"\nCurrent user context: {json.dumps(context)}"
        lc = [_SM(content=system)] + [
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

    effective_thread_id = thread_id if thread_id is not None else str(uuid.uuid4())
    config = {
        "configurable": {"thread_id": effective_thread_id},
        "recursion_limit": MAX_TOOL_ITERATIONS * 2 + 2,
    }

    graph = _build_graph(llm, tools)
    lc_messages = _prepare_input_messages(messages, context, thread_id)

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
                        yield {"event": "token", "data": getattr(last, "content", "")}
                        yield {"event": "done"}
                elif node_name == "tools":
                    for tm in msgs:
                        name = getattr(tm, "name", "")
                        summary: Dict[str, Any] = {"name": name}
                        try:
                            parsed = json.loads(tm.content)
                            summary["code"] = parsed.get("code")
                            if name == "make_chart" and isinstance(parsed.get("result"), dict):
                                yield {"event": "card", "data": parsed["result"]}
                            if name == "highlight_lineage" and isinstance(parsed.get("result"), dict):
                                yield {"event": "ui:highlight", "data": parsed["result"]}
                        except Exception:
                            pass
                        yield {"event": "tool_result", "data": summary}
    except Exception as e:
        logger.exception(e)
        yield {"event": "error", "data": str(e)}
