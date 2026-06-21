"""LLM chat orchestration for the webservice: LangGraph + MemorySaver tool-calling loop."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, Generator, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, MessagesState, StateGraph

from langgraph.errors import GraphRecursionError

from flowcept.agents.prompts.chat_prompts import build_chat_system_prompt
from flowcept.agents.mcp.mcp_client import run_tool
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import sanitize_json_like
from flowcept.commons.vocabulary import PROV_AGENT
from flowcept.configs import AGENT_CHAT_MAX_TOOL_ITERATIONS, AGENT_CHAT_MAX_TOOL_RESULT_CHARS, INSTRUMENTATION_ENABLED

MAX_TOOL_ITERATIONS = AGENT_CHAT_MAX_TOOL_ITERATIONS
# Cap individual tool result strings fed into LangGraph state to prevent context overflow.
_MAX_TOOL_RESULT_CHARS = AGENT_CHAT_MAX_TOOL_RESULT_CHARS
CHAT_WORKFLOW_NAME = "Flowcept LangGraph Chat"

# Module-level saver — persists across requests keyed by thread_id.
_memory = MemorySaver()


def _build_langchain_tools(context: Optional[Dict[str, Any]], allow_dashboard_edit: bool):
    """Wrap MCP tools as LangChain tools."""
    from langchain_core.tools import tool

    def _run_mcp(tool_name: str, **kwargs) -> str:
        return run_tool(tool_name, kwargs=kwargs)[0]

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

    def _scoped_filter(filter: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Apply workflow/campaign scope from the HTTP context."""
        scoped = dict(filter or {})
        for key in ("workflow_id", "campaign_id"):
            if (context or {}).get(key):
                scoped[key] = context[key]
        return scoped

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
        return _run_mcp(
            "query_tasks",
            filter=_scoped_filter(filter),
            projection=_coerce_projection(projection),
            limit=limit,
            sort=_coerce_sort(sort),
        )

    @tool
    def query_workflows(filter: Optional[Dict[str, Any]] = None, limit: int = 100) -> str:
        """Query workflow provenance records with a Mongo-style filter."""
        return _run_mcp("query_workflows", filter=_scoped_filter(filter), limit=limit)

    @tool
    def get_task_summary(filter: Optional[Dict[str, Any]] = None) -> str:
        """Summarize tasks: status counts, per-activity durations, and time range."""
        return _run_mcp("get_task_summary", filter=_scoped_filter(filter))

    @tool
    def list_campaigns(campaign_id: Optional[str] = None) -> str:
        """List derived campaign summaries (campaigns group workflows and tasks).

        campaign_id: when provided, returns only that campaign's summary.
        Always pass the campaign_id from the user context to scope the result.
        """
        effective_id = campaign_id or (context or {}).get("campaign_id")
        return _run_mcp("list_campaigns", campaign_id=effective_id)

    @tool
    def list_agents() -> str:
        """List derived agent summaries (agents observed in task provenance).

        Automatically scoped to the current workflow when workflow_id is in context.
        """
        workflow_id = (context or {}).get("workflow_id")
        effective_filter = {"workflow_id": workflow_id} if workflow_id else None
        return _run_mcp("list_agents", filter=effective_filter)

    @tool
    def make_chart(card_spec: Dict[str, Any]) -> str:
        """Build a chart from a declarative dashboard card spec; the UI renders the result."""
        scoped_spec = dict(card_spec)
        data_spec = dict(scoped_spec.get("data") or {})
        data_spec["filter"] = _scoped_filter(data_spec.get("filter"))
        scoped_spec["data"] = data_spec
        return _run_mcp("make_chart", card_spec=scoped_spec, context=None)

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
        return _run_mcp("highlight_lineage", task_ids=ids, filter=filter, workflow_id=wf_id)

    def _query_text(query: Any) -> str:
        if isinstance(query, str):
            return query
        return json.dumps(query, default=str)

    @tool("generate_result_df")
    def generate_result_df(query: Any) -> str:
        """Answer a natural-language question using the MCP server's in-memory task DataFrame."""
        return _run_mcp("run_df_query", query=_query_text(query), plot=False, context_kind="tasks")

    @tool("generate_plot_code")
    def generate_plot_code(query: Any = None, card_spec: Optional[Dict[str, Any]] = None) -> str:
        """Generate plotting output using the MCP server's in-memory task DataFrame."""
        query_payload = query if query is not None else card_spec
        return _run_mcp("run_df_query", query=_query_text(query_payload), plot=True, context_kind="tasks")

    @tool
    def extract_or_fix_python_code(raw_text: str, runtime_error: Optional[str] = None) -> str:
        """Extract or repair pandas code using the MCP server's in-memory task DataFrame columns."""
        return _run_mcp(
            "extract_or_fix_python_code",
            raw_text=raw_text,
            runtime_error=runtime_error,
            context_kind="tasks",
        )

    @tool
    def get_workflow_context() -> str:
        """Return the workflow record(s) loaded in the agent's in-memory context (DF path counterpart to query_workflows)."""
        return _run_mcp("get_workflow_context")

    db_tools = [
        query_tasks,
        query_workflows,
        get_task_summary,
        list_campaigns,
        list_agents,
        make_chart,
        highlight_lineage,
    ]
    df_tools = [
        generate_result_df,
        generate_plot_code,
        extract_or_fix_python_code,
        get_workflow_context,
        list_agents,
    ]
    tool_context = (context or {}).get("tool_context", "db")
    if tool_context == "df":
        tools = df_tools
    else:
        tools = db_tools

    if allow_dashboard_edit:

        @tool
        def get_dashboard(dashboard_id: str) -> str:
            """Get a stored dashboard spec by id."""
            return _run_mcp("get_dashboard", dashboard_id=dashboard_id)

        @tool
        def update_dashboard(dashboard_id: str, spec: Dict[str, Any]) -> str:
            """Replace a stored dashboard spec with a complete revised spec."""
            return _run_mcp("update_dashboard", dashboard_id=dashboard_id, spec=spec)

        tools += [get_dashboard, update_dashboard]
    return tools


def _with_workflow_schema_context(context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Attach MCP-owned workflow schema context to chat context when available."""
    if not context or not context.get("workflow_id"):
        return context
    enriched = dict(context)
    try:
        payload = json.loads(run_tool("get_workflow_schema_context", kwargs={"workflow_id": context["workflow_id"]})[0])
        if payload.get("code", 500) < 400 and isinstance(payload.get("result"), dict):
            enriched["workflow_schema_context"] = payload["result"].get("prompt_context")
    except Exception:
        return enriched
    return enriched


def _build_graph(llm, tools, agent_id: Optional[str] = None, require_first_tool: bool = False):
    """Build a LangGraph agent + tools graph compiled with the module-level MemorySaver."""
    bound = llm.bind_tools(tools)
    first_bound = llm.bind_tools(tools, tool_choice="required") if require_first_tool else bound
    tools_by_name = {t.name: t for t in tools}

    def _needs_first_tool(state: MessagesState) -> bool:
        return require_first_tool and not any(isinstance(message, ToolMessage) for message in state["messages"])

    def _latest_user_text(state: MessagesState) -> str:
        for message in reversed(state["messages"]):
            if isinstance(message, HumanMessage):
                return str(message.content)
        return ""

    def _tool_calls_for_text(text: str) -> List[Dict[str, Any]]:
        lower = text.lower()
        names = set(tools_by_name)
        has_specific_value = any(marker in lower for marker in ("task_id", "object_id", "workflow_id"))
        if "generate_result_df" in names and any(word in lower for word in ("submit", "submitted", "producer", "produced")):
            # Pattern B: general attribution — query starts with "which/what" (no specific lookup
            # value) and asks about the agent. list_agents alone is sufficient.
            if (
                "list_agents" in names
                and "agent" in lower
                and not has_specific_value
                and lower.strip().startswith(("which ", "what "))
            ):
                return [{"name": "list_agents", "args": {}, "id": str(uuid.uuid4())}]
            query = (
                text
                + "\nInterpret submission/producer questions through provenance dataflow: "
                "find upstream task rows whose generated.* values match used.* values consumed by the target activity, "
                "then return the upstream activity_id and agent_id. "
                "For work-item submission, prefer producer tasks with generated list/dict descriptors that map to "
                "target used identifiers or parameters; do not treat dataset/file/artifact producers as submitters "
                "unless the user explicitly asks about data artifacts. "
                "If the named value appears inside a list of dictionaries in a generated.* field, "
                "extract the full matching dictionary and include its key-value fields."
            )
            tool_calls = [{"name": "generate_result_df", "args": {"query": query}, "id": str(uuid.uuid4())}]
            if "list_agents" in names:
                tool_calls.append({"name": "list_agents", "args": {}, "id": str(uuid.uuid4())})
            return tool_calls
        if "list_agents" in names and "agent" in lower and not has_specific_value:
            return [{"name": "list_agents", "args": {}, "id": str(uuid.uuid4())}]
        if "get_task_summary" in names and any(
            phrase in lower
            for phrase in (
                "lineage",
                "data flow",
                "execution order",
                "how many",
                "count",
                "summary",
                "duration",
            )
        ):
            return [{"name": "get_task_summary", "args": {}, "id": str(uuid.uuid4())}]
        if "make_chart" in names and any(word in lower for word in ("plot", "chart", "graph")):
            return [{
                "name": "make_chart",
                "args": {
                    "card_spec": {
                        "chart_id": "chat-chart",
                        "type": "chart",
                        "title": text,
                        "data": {
                            "source": "tasks",
                            "group_by": "activity_id",
                            "metrics": [{"agg": "count"}],
                        },
                        "viz": {"kind": "bar"},
                    }
                },
                "id": str(uuid.uuid4()),
            }]
        if "extract_or_fix_python_code" in names and ("fix" in lower or "python code" in lower or "dataframe" in lower):
            return [{"name": "extract_or_fix_python_code", "args": {"raw_text": text}, "id": str(uuid.uuid4())}]
        if "generate_plot_code" in names and any(word in lower for word in ("plot", "chart", "graph")):
            return [{"name": "generate_plot_code", "args": {"query": text}, "id": str(uuid.uuid4())}]
        if "generate_result_df" in names and any(word in lower for word in ("lineage", "execution order", "data flow")):
            query = (
                text
                + "\nThe user is asking for workflow lineage/order. Return the ordered distinct activity_id values "
                "from the workflow, using task timestamps or row order when timestamps are unavailable. "
                "Include upstream, target, and downstream activities; do not answer only with metric-matching rows."
            )
            return [{"name": "generate_result_df", "args": {"query": query}, "id": str(uuid.uuid4())}]
        if "generate_result_df" in names and any(
            word in lower
            for word in (
                "activity",
                "agent",
                "count",
                "how many",
                "lineage",
                "task",
            )
        ):
            return [{"name": "generate_result_df", "args": {"query": text}, "id": str(uuid.uuid4())}]
        if "query_workflows" in names and "workflow" in lower:
            return [{"name": "query_workflows", "args": {}, "id": str(uuid.uuid4())}]
        if "get_workflow_context" in names and any(word in lower for word in ("workflow", "workflows")):
            # DF path: workflow records live in the MCP context object, not the tasks DataFrame.
            # get_workflow_context is the DF-path counterpart to query_workflows.
            return [{"name": "get_workflow_context", "args": {}, "id": str(uuid.uuid4())}]
        if "generate_result_df" in names:
            return [{"name": "generate_result_df", "args": {"query": text}, "id": str(uuid.uuid4())}]
        return [{"name": next(iter(tools_by_name)), "args": {}, "id": str(uuid.uuid4())}]

    def _enforce_first_tool(response: AIMessage, state: MessagesState) -> AIMessage:
        if not _needs_first_tool(state):
            return response
        return AIMessage(content="", tool_calls=_tool_calls_for_text(_latest_user_text(state)))

    if INSTRUMENTATION_ENABLED and agent_id is not None:
        from flowcept.instrumentation.flowcept_agent_task import FlowceptLLM
        from flowcept.instrumentation.task_capture import FlowceptTask

        # workflow_id is resolved automatically from Flowcept.current_workflow_id
        # which is set by the Flowcept context in run_chat.
        instrumented_llm = FlowceptLLM(bound, agent_id=agent_id, return_response_object=True)

        def call_model(state: MessagesState):
            """Agent node: invoke the LLM with current messages (instrumented)."""
            active_llm = (
                FlowceptLLM(first_bound, agent_id=agent_id, return_response_object=True)
                if _needs_first_tool(state)
                else instrumented_llm
            )
            return {"messages": [_enforce_first_tool(active_llm.invoke(state["messages"]), state)]}

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
            return {"messages": [_enforce_first_tool(response, state)]}

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
    context = _with_workflow_schema_context(context)
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
    # Chat owns its persistence lifecycle so HTTP requests, tests, and deployed
    # webservice instances all record agent provenance without external state.
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
                            yield {"event": "token", "data": getattr(last, "content", "")}
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
                    # Synthesis failed — surface raw tool results so the caller gets a 200
                    yield {"event": "token", "data": "\n\n".join(accumulated_tool_results[:3])}
            else:
                yield {"event": "error", "data": "Reached tool call limit without retrieving any data."}
            yield {"event": "done"}
        except Exception as e:
            logger.exception(e)
            yield {"event": "error", "data": str(e)}
