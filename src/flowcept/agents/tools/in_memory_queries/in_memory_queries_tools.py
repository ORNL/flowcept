import numpy as np
import json
import pandas as pd
from flowcept.agents.agents_utils import ToolResult, build_llm_model
from flowcept.agents.flowcept_ctx_manager import mcp_flowcept, ctx_manager
from flowcept.agents.prompts.in_memory_query_prompts import generate_plot_code_prompt, extract_or_fix_json_code_prompt, \
    generate_pandas_code_prompt, dataframe_summarizer_context, extract_or_fix_python_code_prompt

from flowcept.agents.tools.in_memory_queries.pandas_agent_utils import safe_execute, safe_json_parse, normalize_output, \
    format_result_df, summarize_df


@mcp_flowcept.tool()
def run_df_query(llm, query: str, plot=False) -> ToolResult:
    ctx = mcp_flowcept.get_context()
    df: pd.DataFrame = ctx.request_context.lifespan_context.df
    schema = ctx.request_context.lifespan_context.tasks_schema
    value_examples = ctx.request_context.lifespan_context.value_examples
    if df is None or not len(df):
        return ToolResult(code=404, result="Current df is empty or null.")

    if "save" in query:
        return save_df(df, schema, value_examples)

    if plot:
        return generate_plot_code(llm, query, schema, value_examples, df)
    else:
        return generate_result_df(llm, query, schema, value_examples, df)


@mcp_flowcept.tool()
def generate_plot_code(llm, query, dynamic_schema, value_examples, df) -> ToolResult:
    plot_prompt = generate_plot_code_prompt(query, dynamic_schema, value_examples)
    try:
        response = llm(plot_prompt)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=plot_prompt)

    result_code, plot_code = None, None
    try:
        result = safe_json_parse(response)
        result_code = result["result_code"]
        plot_code = result["plot_code"]

    except ValueError:
        tool_response = extract_or_fix_json_code(llm, response)
        response = tool_response.result
        if tool_response.code == 201:
            try:
                result = safe_json_parse(response)
                assert "result_code" in result
                assert "plot_code" in result
                ToolResult(code=301, result=result, extra=plot_prompt)
            except ValueError as e:
                return ToolResult(code=405, result=f"Tried to parse this as JSON: {response}, but got Error: {e}", extra=plot_prompt)
            except AssertionError as e:
                return ToolResult(code=405, result=str(e), extra=plot_prompt)

        else:
            return ToolResult(code=499, result=tool_response.result)
    except AssertionError as e:
        return ToolResult(code=405, result=str(e), extra=plot_prompt)
    except Exception as e:
        return ToolResult(code=499, result=str(e), extra=plot_prompt)

    try:
        result_df = safe_execute(df, result_code)
    except Exception as e:
        return ToolResult(code=406, result=str(e))
    try:
        result_df = format_result_df(result_df)
    except Exception as e:
        return ToolResult(code=404, result=str(e))

    this_result = {
        "result_df": result_df,
        "plot_code": plot_code,
        "result_code": result_code
    }
    return ToolResult(code=301, result=this_result, tool_name=generate_plot_code.__name__)


@mcp_flowcept.tool()
def generate_result_df(llm, query: str, dynamic_schema, example_values, df):
    try:
        prompt = generate_pandas_code_prompt(query, dynamic_schema, example_values)
        response = llm(prompt)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=prompt)

    try:
        result_code = response
        result_df = safe_execute(df, result_code)
    except Exception as e:
        tool_result = extract_or_fix_python_code(llm, result_code)
        if tool_result.code == 201:
            new_result_code = tool_result.result
            try:
                result_df = safe_execute(df, new_result_code)
            except Exception as e:
                return ToolResult(code=405, result=f"Failed to parse this as Python code: {result_code}."
                                                   f"Then tried to LLM extract the Python code, got {new_result_code}"
                                                   f"but got error {e}")

        else:
            return ToolResult(code=405, result=f"Failed to parse this as Python code: {result_code}."
                                               f"Exception: {e}\n"
                                               f"Then tried to LLM extract the Python code, but got error:"
                                               f" {tool_result.result}")

    try:
        result_df = normalize_output(result_df)
    except Exception as e:
        return ToolResult(code=405, result=str(e))

    result_df = result_df.dropna(axis=1, how='all')

    summary, summary_error = None, None
    try:
        tool_result = summarize_result(llm, result_code, result_df, query)
        if tool_result.is_success():
            return_code = 301
            summary = tool_result.result
        else:
            return_code = 302
            summary_error = tool_result.result
    except Exception as e:
        ctx_manager.logger.exception(e)
        summary = ""
        summary_error = str(e)
        return_code = 303

    try:
        result_df = format_result_df(result_df)
    except Exception as e:
        return ToolResult(code=405, result=str(e))

    this_result = {
        "result_code": result_code,
        "result_df": result_df,
        "summary": summary,
        "summary_error": summary_error,
    }
    return ToolResult(code=return_code, result=this_result, tool_name=generate_result_df.__name__)


@mcp_flowcept.tool()
def extract_or_fix_python_code(llm, raw_text):
    prompt = extract_or_fix_python_code_prompt(raw_text)
    try:
        response = llm(prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def extract_or_fix_json_code(llm, raw_text) -> ToolResult:
    prompt = extract_or_fix_json_code_prompt(raw_text)
    try:
        response = llm(prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def summarize_result(llm, code, result, query: str) -> ToolResult:
    """
    Summarize the pandas result with local reduction for large DataFrames.
    - For wide DataFrames, selects top columns based on variance and uniqueness.
    - For long DataFrames, truncates to preview rows.
    - Constructs a detailed prompt for the LLM with original column context.
    """

    summarized_df = summarize_df(result, code)
    prompt = dataframe_summarizer_context(code, summarized_df, query)
    try:
        response = llm(prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=400, result=str(e))


@mcp_flowcept.tool()
def save_df(df, schema, value_examples):
    with open('/tmp/current_tasks_schema.json', 'w') as f:
        json.dump(schema, f, indent=2)
    with open('/tmp/value_examples.json', 'w') as f:
        json.dump(value_examples, f, indent=2)
    df.to_csv("/tmp/current_agent_df.csv", index=False)
    return ToolResult(code=201, result="Saved df and schema to /tmp directory")


@mcp_flowcept.tool()
def query_on_saved_df(query: str, dynamic_schema_path, value_examples_path, df_path):
    df = pd.read_csv(df_path)
    with open(dynamic_schema_path) as f:
        dynamic_schema = json.load(f)

    with open(value_examples_path) as f:
        value_examples = json.load(f)

    llm = build_llm_model()
    return generate_result_df(llm, query, dynamic_schema, value_examples, df)
