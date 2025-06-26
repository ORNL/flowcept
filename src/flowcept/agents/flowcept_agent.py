import json
import os
from typing import Dict, List, Union
import pandas as pd
import uvicorn
from flowcept.flowceptor.agents.in_memory_queries.pandas_agent_utils import clean_code, safe_execute, \
    summarize_result, normalize_output, fix_code, generate_pandas_code2, generate_plot_code, extract_or_fix_json_code
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.prompts import base

from flowcept.configs import AGENT
from flowcept.flowcept_api.flowcept_controller import Flowcept
from flowcept.agents.agents_utils import (
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

os.environ["SAMBASTUDIO_URL"] = AGENT.get("llm_server_url")
os.environ["SAMBASTUDIO_API_KEY"] = AGENT.get("api_key")

agent_controller = FlowceptAgentContextManager()
mcp = FastMCP("FlowceptAgent", require_session=False, lifespan=agent_controller.lifespan, stateless_http=True)

#################################################
# PROMPTS
#################################################



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

    plot_code = None
    if plot:
        original_prompt, result, success = generate_plot_code(query, schema)
        if success:
            code = result.get("result_code")
            plot_code = result.get("plot_code")
        else:
            if "failed to parse JSON" in result:
                result = extract_or_fix_json_code(result)  # TODO error check
                code = result.get("result_code")
                plot_code = result.get("plot_code")
            else:
                return {"error": result, "msg_only": True}
    else:
        original_prompt, code, success = generate_pandas_code2(query, schema)

    print("🖥️ Generated Code:\n", code)
    if not success:
        return {"error": code, "msg_only": True}

    result, error = safe_execute(df, code)

    if error:

        # Try again:
        code = fix_code(original_prompt, code, error)
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
    return {"code": code, "result": result, "summary": summary, "error": None, "msg_only": False, "plot_code": plot_code}


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
