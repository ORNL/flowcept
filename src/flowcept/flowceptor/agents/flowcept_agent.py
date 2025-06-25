import json
import os
from typing import Dict, List, Union
import pandas as pd
import uvicorn
from flowcept.flowceptor.agents.in_memory_queries.pandas_agent_utils import clean_code, safe_execute, \
    summarize_result, normalize_output, fix_code, generate_pandas_code2
#from langchain.chains.retrieval_qa.base import RetrievalQA
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

from flowcept.configs import AGENT
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.flowceptor.agents.agents_utils import (
    convert_mcp_to_langchain,
    build_llm_model,
)
from flowcept.flowceptor.agents.flowcept_llm_prov_capture import (
    invoke_llm,
    add_preamble_to_response,
)
from flowcept.flowceptor.agents.prompts import (
    get_question_prompt,
    BASE_MULTITASK_PROMPT,
    BASE_SINGLETASK_PROMPT, ROUTING_PROMPT, SMALL_TALK_PROMPT,
)
from flowcept.flowceptor.agents.flowcept_agent_context_manager import FlowceptAgentContextManager
#from flowcept.flowceptor.agents.flowcept_qa_manager import FlowceptQAManager

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")

agent_controller = FlowceptAgentContextManager()
mcp = FastMCP("FlowceptAgent", require_session=False, lifespan=agent_controller.lifespan, stateless_http=True)

#################################################
# PROMPTS
#################################################


@mcp.prompt()
def single_task_used_generated_prompt(task_data: Dict, question: str) -> list[base.Message]:
    """
    Generate a prompt for analyzing a single task's provenance and resource usage.

    Parameters
    ----------
    task_data : dict
        The task object containing provenance and telemetry fields.
    question : str
        A specific question to ask about the task.

    Returns
    -------
    list of base.Message
        The structured prompt messages for LLM analysis.
    """
    msgs = BASE_SINGLETASK_PROMPT.copy()
    msgs.append(get_question_prompt(question))
    msgs.append(base.UserMessage(f"This is the task object I need you to focus on: \n {task_data}\n"))
    return msgs


@mcp.prompt()
def multi_task_summary_prompt(task_list: List[Dict]) -> List[base.Message]:
    """
    Generate a prompt for analyzing multiple task objects in a workflow.

    Parameters
    ----------
    task_list : list of dict
        A list of task objects with provenance and telemetry data.

    Returns
    -------
    list of base.Message
        The structured prompt messages for the LLM.
    """
    messages = BASE_MULTITASK_PROMPT.copy()
    pretty_tasks = json.dumps(task_list, indent=2, default=str)
    messages.append(base.UserMessage(f"These are the tasks I need you to reason about:\n\n{pretty_tasks}\n\n"))
    return messages


@mcp.prompt()
def multi_task_qa_prompt(question: str) -> List[base.Message]:
    """
    Generate a prompt for asking a specific question about multiple tasks.

    Parameters
    ----------
    question : str
        The user's query about task data.

    Returns
    -------
    list of base.Message
        Prompt messages structured for the LLM.
    """
    messages = BASE_MULTITASK_PROMPT.copy()
    messages.append(get_question_prompt(question))
    return messages


#################################################
# TOOLS
#################################################


@mcp.tool()
def analyze_task_chunk() -> str:
    """
    Analyze a recent chunk of tasks using an LLM to detect patterns or anomalies.

    Returns
    -------
    str
        LLM-generated analysis of the selected task chunk.
    """
    LAST_K = 5  # TODO make this dynamic from config
    ctx = mcp.get_context()
    task_list = ctx.request_context.lifespan_context.task_summaries[:-LAST_K]
    agent_controller.logger.debug(f"N Tasks = {len(task_list)}")
    if not task_list:
        return "No tasks available."

    messages = multi_task_summary_prompt(task_list)
    langchain_messages = convert_mcp_to_langchain(messages)
    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp, task_data=None)
    agent_controller.logger.debug(f"Result={result}")
    return result


# @mcp.tool()
# def ask_about_tasks_buffer(question: str) -> str:
#     """
#     Use a QA chain to answer a question about the current task buffer.
#
#     Parameters
#     ----------
#     question : str
#         The question to ask about the buffered tasks.
#
#     Returns
#     -------
#     str
#         Answer from the QA chain or an error message.
#     """
#     ctx = mcp.get_context()
#     qa_chain = build_qa_chain_from_ctx(ctx)
#     if not qa_chain:
#         return "No tasks available."
#
#     messages = multi_task_qa_prompt(question)
#
#     try:
#         query_str = convert_mcp_messages_to_plain_text(messages)
#     except Exception as e:
#         agent_controller.logger.exception(e)
#         return f"An internal error happened: {e}"
#
#     response = invoke_qa_question(qa_chain, query_str=query_str)
#     agent_controller.logger.debug(f"Response={response}")
#     return response


# def build_qa_chain_from_ctx(ctx) -> RetrievalQA:
#     """
#     Build or retrieve a QA chain from the current request context.
#
#     Parameters
#     ----------
#     ctx : RequestContext
#         The current MCP request context.
#
#     Returns
#     -------
#     RetrievalQA or None
#         A QA chain built from vectorstore metadata, or None if unavailable.
#     """
#     qa_chain = ctx.request_context.lifespan_context.qa_chain
#     if not qa_chain:
#         vectorstore_path = "/tmp/qa_index" #ctx.request_context.lifespan_context.vectorstore_path
#         agent_controller.logger.debug(f"Path: {vectorstore_path}")
#         qa_chain = FlowceptQAManager.build_qa_chain_from_vectorstore_path(vectorstore_path)
#         if not qa_chain:
#             return None
#     return qa_chain


@mcp.tool()
def get_latest(n: int = None) -> str:
    """
    Return the most recent task(s) from the task buffer.

    Parameters
    ----------
    n : int, optional
        Number of most recent tasks to return. If None, return only the latest.

    Returns
    -------
    str
        JSON-encoded task(s).
    """
    ctx = mcp.get_context()
    tasks = ctx.request_context.lifespan_context.tasks
    if not tasks:
        return "No tasks available."
    if n is None:
        return json.dumps(tasks[-1])
    return json.dumps(tasks[-n])


@mcp.tool()
def check_liveness() -> str:
    """
    Confirm the agent is alive and responding.

    Returns
    -------
    str
        Liveness status string.
    """
    return f"I'm {mcp.name} and I'm ready!"


@mcp.tool()
def check_llm() -> str:
    """
    Check connectivity and response from the LLM backend.

    Returns
    -------
    str
        LLM response, formatted with MCP metadata.
    """
    messages = [base.UserMessage("Hi, are you working properly?")]

    langchain_messages = convert_mcp_to_langchain(messages)
    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp)

    return result

@mcp.tool()
def prompt_handler(message: str) -> Union[str, Dict]:

    """
    Routes a user message using an LLM to classify its intent.

    Parameters
    ----------
    message : str
        User's natural language input.

    Returns
    -------
    TextContent
        The AI response or routing feedback.
    """
    # routes = {
    #     "small_talk": ["hi", "hello", "thanks", "bye"],
    #     "plot": ["plot", "chart", "graph", "visualize"],
    #     "in_memory": ["current", "context", "recent"],
    #     "history": [],
    # }
    #
    #
    # words = set(re.findall(r"\b\w+\b", message.lower()))
    #
    # for route, keywords in routes.items():
    #     if any(kw in words for kw in keywords):
    #         return route
    #
    # lower_msg = message.lower()
    #
    # for route, keywords in routes.items():
    #     if any(kw in lower_msg for kw in keywords):
    #         return route

    llm = build_llm_model()
    prompt = ROUTING_PROMPT + message
    route = llm.invoke(prompt)

    if route == "small_talk":
        prompt = SMALL_TALK_PROMPT + message
        response = llm.invoke(prompt)
    elif route == "plot":
        response = run_df_query(message, plot=True)
    elif route == "historical_prov_query":
        response = "We need to query the Provenance Database"
    elif route == "in_context_query":
        response = run_df_query(message)

    elif route == "in_chat_query":
        response = llm.invoke(prompt) # TODO needs chat context
    else:
        response = "I don't know how to route."

    return response

@mcp.tool()
def ask_about_latest_task(question) -> str:
    """
    Ask a question specifically about the latest task in the buffer.

    Parameters
    ----------
    question : str
        A user-defined question to analyze the latest task.

    Returns
    -------
    str
        Response from the LLM based on the latest task.
    """
    ctx = mcp.get_context()
    tasks = ctx.request_context.lifespan_context.task_summaries
    if not tasks:
        return "No tasks available."
    task_data = tasks[-1]

    messages = single_task_used_generated_prompt(task_data, question)

    langchain_messages = convert_mcp_to_langchain(messages)

    response = invoke_llm(langchain_messages)
    result = add_preamble_to_response(response, mcp, task_data)
    return result


@mcp.tool()
def run_df_query(query: str, plot=False):
    ctx = mcp.get_context()
    df: pd.DataFrame = ctx.request_context.lifespan_context.df
    schema = ctx.request_context.lifespan_context.tasks_schema
    #condensed_schema = ctx.request_context.lifespan_context.condensed_schema
    if df is None or not len(df):
        return {
            "result": "Current df is either empty or null",
            "msg_only": True
        }

    print(f"\n🔍 Query: {query}")

    if "save" in query:
        with open('/tmp/current_tasks_schema.json', 'w') as f:
            json.dump(schema, f, indent=2)
        df.to_csv("/tmp/current_agent_df.csv", index=False)
        return {
            "result": "Saved dataframe into /tmp/current_agent_df.csv",
            "msg_only": True
        }
    #original_prompt, code, success = generate_pandas_code3(query, condensed_schema)
    original_prompt, code, success = generate_pandas_code2(query, schema)
    print("🖥️ Generated Code:\n", code)
    if not success:
        return {"error": code, "msg_only": True}

    code = clean_code(code)
    result, error = safe_execute(df, code)
    if error:

        # Try again:
        code = fix_code(original_prompt, code, error)
        code = clean_code(code)
        result, error = safe_execute(df, code)

        print("❌ Execution Error:", error)
        return {"code": code, "error": error}
    result = normalize_output(result)
    if result is None:
        return {"code": code, "result": None, "summary": "", "error": "Code returned null.", "msg_only": False}
    result = result.dropna(axis=1, how='all')
    print("📈 Result:\n", result)
    try:
        summary = summarize_result(code, result, df.columns, query)
    except Exception as e:
        agent_controller.logger.exception(e)
        summary = "❌ Summary Error: " + str(e)

    if len(result) > 100:
        agent_controller.logger.warning("Result set is too long. We are only going to send the head.")
        # TODO deal with very long results later
        result = result.head(100)
    result = result.to_csv(index=False)
    return {"code": code, "result": result, "summary": summary, "error": None, "msg_only": False}


def main():
    """
    Start the MCP server.
    """
    f = Flowcept(start_persistence=False, save_workflow=False, check_safe_stops=False).start()
    f.logger.info(f"This section's workflow_id={Flowcept.current_workflow_id}")
    uvicorn.run(
        mcp.streamable_http_app, host=AGENT.get("mcp_host", "0.0.0.0"), port=AGENT.get("mcp_port", 8000), lifespan="on"
    )


if __name__ == "__main__":
    main()
