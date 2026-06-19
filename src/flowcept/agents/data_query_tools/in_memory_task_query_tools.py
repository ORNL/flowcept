"""Plain-Python in-memory task query tools.

Functions in this module operate on pandas DataFrames and do NOT import from the
MCP framework (no ``@mcp_flowcept.tool()``). The MCP layer lives in
``mcp_tools/in_memory_task_query_mcp_tools.py``.
"""

import json
from flowcept.agents.tool_result import ToolResult
from flowcept.agents.llm.builders import build_llm_model
from flowcept.agents.data_query_tools.tools_utils import query_runtime_retry
from flowcept.commons.flowcept_logger import FlowceptLogger

from flowcept.agents.data_query_tools.pandas_utils import (
    load_saved_df,
    safe_execute,
    safe_json_parse,
    normalize_output,
    format_result_df,
    summarize_df,
)

from flowcept.agents.prompts.in_memory_task_query_prompts import (
    build_plot_code_prompt,
    extract_or_fix_json_code_prompt,
    build_pandas_code_prompt,
    build_dataframe_summarizer_prompt,
    build_extract_or_fix_python_code_prompt,
)

EMPTY_DF_MESSAGE = "Current df is empty or null."


def _call_llm(llm, prompt: str) -> str:
    """Call an LLM with a string prompt and always return a plain string.

    Handles both ``FlowceptLLM`` (whose ``invoke`` already returns ``str``)
    and raw LangChain models (whose ``invoke`` returns an ``AIMessage``).
    """
    response = llm.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)


def run_df_query(
    query: str,
    df,
    schema,
    value_examples,
    custom_user_guidance,
    llm=None,
    plot=False,
    context_kind: str = "tasks",
) -> ToolResult:
    r"""Run a natural language query against a DataFrame.

    Parameters
    ----------
    query : str
        Natural language query or Python code snippet.
    df : pandas.DataFrame
        The DataFrame to query.
    schema : dict
        Schema of the DataFrame.
    value_examples : dict
        Example values for each field.
    custom_user_guidance : list
        Custom guidance strings from the user.
    llm : callable, optional
        LLM callable. Built from settings if None.
    plot : bool, optional
        If True, generate plotting code.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    ToolResult
    """
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE)
    if "save" in query:
        return save_df(df, schema, value_examples)
    if "result = df" in query:
        return run_df_code(user_code=query, df=df)

    if plot:
        return generate_plot_code(
            llm,
            query,
            schema,
            value_examples,
            df,
            custom_user_guidance=custom_user_guidance,
            context_kind=context_kind,
        )
    return generate_result_df(
        llm,
        query,
        schema,
        value_examples,
        df,
        custom_user_guidance=custom_user_guidance,
        context_kind=context_kind,
    )


def execute_df_code(user_code: str, df) -> ToolResult:
    """Execute externally generated pandas code against a DataFrame.

    Parameters
    ----------
    user_code : str
        Pandas code expected to assign output to ``result``.
    df : pandas.DataFrame
        DataFrame to execute against.

    Returns
    -------
    ToolResult
    """
    if df is None or not len(df):
        return ToolResult(code=404, result=EMPTY_DF_MESSAGE)
    return run_df_code(user_code=user_code, df=df)


def generate_plot_code(
    llm,
    query,
    dynamic_schema,
    value_examples,
    df,
    custom_user_guidance=None,
    context_kind="tasks",
) -> ToolResult:
    """Generate DataFrame and plotting code from a natural language query using an LLM.

    Parameters
    ----------
    llm : callable
        LLM callable.
    query : str
        Natural language query.
    dynamic_schema : dict
        Schema of the DataFrame.
    value_examples : dict
        Example values.
    df : pandas.DataFrame
        The DataFrame.
    custom_user_guidance : list, optional
        Custom guidance strings.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    ToolResult
    """
    plot_prompt = build_plot_code_prompt(
        query,
        dynamic_schema,
        value_examples,
        list(df.columns),
        context_kind=context_kind,
    )
    try:
        response = _call_llm(llm, plot_prompt)
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
                return ToolResult(
                    code=405,
                    result=f"Tried to parse this as JSON: {response}, but got Error: {e}",
                    extra=plot_prompt,
                )
            except AssertionError as e:
                return ToolResult(code=405, result=str(e), extra=plot_prompt)
        else:
            return ToolResult(code=499, result=tool_response.result)
    except AssertionError as e:
        return ToolResult(code=405, result=str(e), extra=plot_prompt)
    except Exception as e:
        return ToolResult(code=499, result=str(e), extra=plot_prompt)

    columns = list(df.columns)
    code_holder = [result_code]
    retry_count = [0]

    def _execute():
        return safe_execute(df, code_holder[0])

    def _fix(exc, attempt):
        tool_result = extract_or_fix_python_code(
            llm, code_holder[0], columns, runtime_error=str(exc)
        )
        if tool_result.code != 201:
            raise RuntimeError(f"LLM could not fix the code: {tool_result.result}")
        code_holder[0] = tool_result.result
        retry_count[0] += 1
        return _execute

    try:
        result_df = query_runtime_retry(_execute, _fix, max_attempts=3)
        result_code = code_holder[0]
    except Exception as e:
        return ToolResult(code=406, result=str(e), extra={"retry_attempts": retry_count[0]})

    try:
        result_df = format_result_df(result_df)
    except Exception as e:
        return ToolResult(code=404, result=str(e))

    return ToolResult(
        code=301,
        result={"result_df": result_df, "plot_code": plot_code, "result_code": result_code},
        tool_name="generate_plot_code",
        extra={"retry_attempts": retry_count[0]},
    )


def generate_result_df(
    llm,
    query: str,
    dynamic_schema,
    example_values,
    df,
    custom_user_guidance=None,
    attempt_fix=True,
    summarize=True,
    context_kind="tasks",
) -> ToolResult:
    """Generate a result DataFrame from a natural language query using an LLM.

    Parameters
    ----------
    llm : callable
        LLM callable. Built from settings if None.
    query : str
        Natural language query.
    dynamic_schema : dict
        Schema of the DataFrame.
    example_values : dict
        Example values.
    df : pandas.DataFrame
        The DataFrame to query.
    custom_user_guidance : list, optional
        Custom guidance strings.
    attempt_fix : bool, optional
        If True, attempt to fix invalid generated code.
    summarize : bool, optional
        If True, summarize the result.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    ToolResult
    """
    _logger = FlowceptLogger()
    if llm is None:
        llm = build_llm_model()
    try:
        prompt = build_pandas_code_prompt(
            query,
            dynamic_schema,
            example_values,
            custom_user_guidance,
            list(df.columns),
            context_kind=context_kind,
        )
        response = _call_llm(llm, prompt)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=prompt)

    result_code = response
    columns = list(df.columns)

    code_holder = [result_code]
    retry_count = [0]

    def _execute():
        return safe_execute(df, code_holder[0])

    def _fix(exc, attempt):
        if not attempt_fix:
            raise exc
        tool_result = extract_or_fix_python_code(
            llm, code_holder[0], columns, runtime_error=str(exc)
        )
        if tool_result.code != 201:
            raise RuntimeError(f"LLM could not fix the code: {tool_result.result}")
        code_holder[0] = tool_result.result
        retry_count[0] += 1
        return _execute

    try:
        result_df = query_runtime_retry(_execute, _fix, max_attempts=3)
        result_code = code_holder[0]
    except Exception as e:
        return ToolResult(
            code=405,
            result=(
                f"Failed to execute after retries: ```python\n{code_holder[0]}```\n"
                f"Last error: {e}"
            ),
            extra={
                "generated_code": code_holder[0],
                "exception": str(e),
                "prompt": prompt,
                "retry_attempts": retry_count[0],
            },
        )

    try:
        result_df = normalize_output(result_df)
    except Exception as e:
        return ToolResult(
            code=504,
            result="Failed to normalize output.",
            extra={"generated_code": result_code, "exception": str(e), "prompt": prompt},
        )

    result_df = result_df.dropna(axis=1, how="all")

    return_code = 301
    summary, summary_error = None, None
    if summarize:
        try:
            tool_result = summarize_result(
                llm,
                result_code,
                result_df,
                query,
                dynamic_schema,
                example_values,
                list(df.columns),
                context_kind=context_kind,
            )
            if tool_result.is_success():
                return_code = 301
                summary = tool_result.result
            else:
                return_code = 302
                summary_error = tool_result.result
        except Exception as e:
            _logger.exception(e)
            summary = ""
            summary_error = str(e)
            return_code = 303

    try:
        result_df_str = format_result_df(result_df)
    except Exception as e:
        return ToolResult(
            code=405,
            result="Failed to format output.",
            extra={"generated_code": result_code, "exception": str(e), "prompt": prompt},
        )

    return ToolResult(
        code=return_code,
        result={
            "result_code": result_code,
            "result_df": result_df_str,
            "result_df_markdown": result_df.to_markdown(index=False),
            "summary": summary,
            "summary_error": summary_error,
        },
        tool_name="generate_result_df",
        extra={"prompt": prompt, "retry_attempts": retry_count[0]},
    )


def run_df_code(user_code: str, df) -> ToolResult:
    """Execute user-provided Python code on a DataFrame and format the result.

    Parameters
    ----------
    user_code : str
        Python code string that operates on the DataFrame.
    df : pandas.DataFrame
        The input DataFrame.

    Returns
    -------
    ToolResult
    """
    try:
        result_df = safe_execute(df, user_code)
    except Exception as e:
        return ToolResult(code=405, result=f"Failed to run this as Python code: {user_code}. Got error {e}")

    try:
        result_df = normalize_output(result_df)
    except Exception as e:
        return ToolResult(code=405, result=str(e))

    result_df = result_df.dropna(axis=1, how="all")
    return ToolResult(
        code=301,
        result={"result_code": user_code, "result_df": format_result_df(result_df)},
        tool_name="run_df_code",
    )


def extract_or_fix_python_code(llm, raw_text, current_fields, runtime_error: str = None) -> ToolResult:
    """Extract or repair Python code from raw text using an LLM.

    Parameters
    ----------
    llm : callable
        LLM callable.
    raw_text : str
        Raw text possibly containing Python code.
    current_fields : list
        Available DataFrame column names.
    runtime_error : str, optional
        Exception message from a previous execution attempt.  When provided,
        the LLM is explicitly asked to fix that runtime error.

    Returns
    -------
    ToolResult
    """
    prompt = build_extract_or_fix_python_code_prompt(raw_text, current_fields, runtime_error=runtime_error)
    try:
        response = _call_llm(llm, prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


def extract_or_fix_json_code(llm, raw_text) -> ToolResult:
    """Extract or repair JSON code from raw text using an LLM.

    Parameters
    ----------
    llm : callable
        LLM callable.
    raw_text : str
        Raw text possibly containing JSON.

    Returns
    -------
    ToolResult
    """
    prompt = extract_or_fix_json_code_prompt(raw_text)
    try:
        response = _call_llm(llm, prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


def summarize_result(
    llm,
    code,
    result,
    query: str,
    dynamic_schema,
    example_values,
    current_fields,
    context_kind="tasks",
) -> ToolResult:
    """Summarize a pandas result with local reduction for large DataFrames.

    Parameters
    ----------
    llm : callable
        LLM callable.
    code : str
        The pandas code that produced the result.
    result : pandas.DataFrame
        The result DataFrame.
    query : str
        The original user query.
    dynamic_schema : dict
        Schema of the DataFrame.
    example_values : dict
        Example values.
    current_fields : list
        Current DataFrame column names.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    ToolResult
    """
    summarized_df = summarize_df(result, code)
    prompt = build_dataframe_summarizer_prompt(
        code,
        summarized_df,
        dynamic_schema,
        example_values,
        query,
        current_fields,
        context_kind=context_kind,
    )
    try:
        response = _call_llm(llm, prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=400, result=str(e))


def save_df(df, schema, value_examples) -> ToolResult:
    """Save a DataFrame, its schema, and example values to temporary files.

    Parameters
    ----------
    df : pandas.DataFrame
        The DataFrame to save.
    schema : dict
        Schema dict.
    value_examples : dict
        Example values dict.

    Returns
    -------
    ToolResult
    """
    with open("/tmp/current_tasks_schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    with open("/tmp/value_examples.json", "w") as f:
        json.dump(value_examples, f, indent=2)
    df.to_csv("/tmp/current_agent_df.csv", index=False)
    return ToolResult(code=201, result="Saved df and schema to /tmp directory")


def query_on_saved_df(query: str, dynamic_schema_path, value_examples_path, df_path):
    """Run a natural language query against a saved DataFrame.

    Parameters
    ----------
    query : str
        Natural language query.
    dynamic_schema_path : str
        Path to a JSON schema file.
    value_examples_path : str
        Path to a JSON example values file.
    df_path : str
        Path to the saved DataFrame CSV file.

    Returns
    -------
    ToolResult
    """
    df = load_saved_df(df_path)
    with open(dynamic_schema_path) as f:
        dynamic_schema = json.load(f)
    with open(value_examples_path) as f:
        value_examples = json.load(f)
    llm = build_llm_model()
    return generate_result_df(llm, query, dynamic_schema, value_examples, df, attempt_fix=False, summarize=False)
