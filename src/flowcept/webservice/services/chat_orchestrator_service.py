"""LLM chat orchestration for the webservice: tool-calling loop over the shared prov tools."""

from __future__ import annotations

import json
from typing import Any, Dict, Generator, List, Optional

from flowcept.agents.prompts.chat_prompts import CHAT_SYSTEM_PROMPT
from flowcept.agents.data_query_tools import db_query_tools as prov_tools
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import AGENT_CHAT_MAX_TOOL_ITERATIONS

MAX_TOOL_ITERATIONS = AGENT_CHAT_MAX_TOOL_ITERATIONS


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
        # Coerce a bare string to a list so the LLM can pass either form.
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


def _build_messages(messages: List[Dict[str, str]], context: Optional[Dict[str, Any]]):
    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

    system = CHAT_SYSTEM_PROMPT
    if context:
        system += f"\nCurrent user context (scope queries with it): {json.dumps(context)}"
    lc_messages = [SystemMessage(content=system)]
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        lc_messages.append(AIMessage(content=content) if role == "assistant" else HumanMessage(content=content))
    return lc_messages


def run_chat(
    llm,
    messages: List[Dict[str, str]],
    context: Optional[Dict[str, Any]] = None,
    allow_dashboard_edit: bool = False,
) -> Generator[Dict[str, Any], None, None]:
    """Run one chat turn as a generator of events.

    Yields dict events: ``{"event": "tool_call"|"tool_result"|"card"|"token"|"done"|"error", ...}``.
    The caller decides whether to stream them (SSE) or collect them into one response.

    Parameters
    ----------
    llm : Any
        A langchain chat model (from ``build_llm_model``).
    messages : list of dict
        Conversation history, ``[{"role": "user"|"assistant", "content": "..."}]``.
    context : dict, optional
        UI context (e.g., ``{"workflow_id": ...}``) injected into the system prompt and charts.
    allow_dashboard_edit : bool, optional
        Whether dashboard-modifying tools are bound.
    """
    logger = FlowceptLogger()
    tools = _build_langchain_tools(context, allow_dashboard_edit)
    tools_by_name = {t.name: t for t in tools}
    lc_messages = _build_messages(messages, context)

    try:
        bound = llm.bind_tools(tools)
    except (NotImplementedError, AttributeError):
        logger.warning("Chat LLM does not support tool binding; answering without tools.")
        bound = None

    try:
        if bound is None:
            response = llm.invoke(lc_messages)
            yield {"event": "token", "data": getattr(response, "content", str(response))}
            yield {"event": "done"}
            return

        for _ in range(MAX_TOOL_ITERATIONS):
            ai_message = bound.invoke(lc_messages)
            tool_calls = getattr(ai_message, "tool_calls", None) or []
            if not tool_calls:
                yield {"event": "token", "data": ai_message.content}
                yield {"event": "done"}
                return

            lc_messages.append(ai_message)
            from langchain_core.messages import ToolMessage

            for call in tool_calls:
                name = call["name"]
                args = call.get("args") or {}
                call_id = call.get("id") or name
                yield {"event": "tool_call", "data": {"name": name, "args": args}}
                tool_fn = tools_by_name.get(name)
                output = tool_fn.invoke(args) if tool_fn is not None else json.dumps({"error": f"Unknown tool {name}"})
                lc_messages.append(ToolMessage(content=output, tool_call_id=call_id))

                summary: Dict[str, Any] = {"name": name}
                try:
                    parsed = json.loads(output)
                    summary["code"] = parsed.get("code")
                    if name == "make_chart" and isinstance(parsed.get("result"), dict):
                        yield {"event": "card", "data": parsed["result"]}
                    if name == "highlight_lineage" and isinstance(parsed.get("result"), dict):
                        yield {"event": "ui:highlight", "data": parsed["result"]}
                except Exception:
                    pass
                yield {"event": "tool_result", "data": summary}

        yield {"event": "token", "data": "I reached the tool-call limit for this request. Please refine the question."}
        yield {"event": "done"}
    except Exception as e:
        logger.exception(e)
        yield {"event": "error", "data": str(e)}
