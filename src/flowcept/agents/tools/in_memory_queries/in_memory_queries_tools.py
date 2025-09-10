import json
import pandas as pd
from flowcept.agents.agents_utils import ToolResult, build_llm_model
from flowcept.agents.flowcept_ctx_manager import mcp_flowcept, ctx_manager
from flowcept.agents.prompts.in_memory_query_prompts import (
    generate_plot_code_prompt,
    extract_or_fix_json_code_prompt,
    generate_pandas_code_prompt,
    dataframe_summarizer_context,
    extract_or_fix_python_code_prompt,
)

from flowcept.agents.tools.in_memory_queries.pandas_agent_utils import (
    load_saved_df,
    safe_execute,
    safe_json_parse,
    normalize_output,
    format_result_df,
    summarize_df,
)


@mcp_flowcept.tool()
def run_df_query(llm, query: str, plot=False) -> ToolResult:
    r"""
    Run a natural language query against the current context DataFrame.

    This tool retrieves the active DataFrame, schema, and example values
    from the MCP Flowcept context and uses an LLM to process the query.
    Depending on the query and flags, it may reset the context, save the
    current DataFrame, execute raw code, generate a result DataFrame, or
    produce plotting code.

    Parameters
    ----------
    llm : callable
        A language model function or wrapper that accepts a prompt string
        and returns a response.
    query : str
        Natural language query or Python code snippet to run against the
        current DataFrame context.
    plot : bool, default=False
        If True, generate plotting code along with a result DataFrame.
        If False, only generate and return the result DataFrame.

    Returns
    -------
    ToolResult
        - ``code=201`` : Context reset or DataFrame/schema saved.
        - ``code=301`` : Successful result DataFrame (and optional plot code).
        - ``code=404`` : No active DataFrame in context.
        - Other codes indicate execution or formatting errors from underlying tools.

    Notes
    -----
    - Querying with "reset context" clears the active DataFrame and resets
      the context.
    - Querying with "save" persists the DataFrame, schema, and example
      values to disk via ``save_df``.
    - Queries containing "result = df" are executed directly as code.
    - With ``plot=True``, the tool delegates to ``generate_plot_code``;
      otherwise, it calls ``generate_result_df``.

    Examples
    --------
    Reset the context:

    >>> run_df_query(llm, "reset context")
    ToolResult(code=201, result="Context Reset!")

    Save the current DataFrame:

    >>> run_df_query(llm, "save")
    ToolResult(code=201, result="Saved df and schema to /tmp directory")

    Generate a result DataFrame:

    >>> run_df_query(llm, "Show average sales by region")
    ToolResult(code=301, result={'result_df': 'region,avg_sales\\nNorth,100\\nSouth,95'})

    Generate a plot along with the DataFrame:

    >>> run_df_query(llm, "Show sales trend as a line chart", plot=True)
    ToolResult(code=301, result={'result_df': '...', 'plot_code': 'plt.plot(...)'})
    """
    ctx = mcp_flowcept.get_context()
    df: pd.DataFrame = ctx.request_context.lifespan_context.df
    schema = ctx.request_context.lifespan_context.tasks_schema
    value_examples = ctx.request_context.lifespan_context.value_examples
    if df is None or not len(df):
        return ToolResult(code=404, result="Current df is empty or null.")

    if "reset context" in query:
        ctx.request_context.lifespan_context.df = pd.DataFrame()
        return ToolResult(code=201, result="Context Reset!")
    elif "save" in query:
        return save_df(df, schema, value_examples)
    elif "result = df" in query:
        return run_df_code(user_code=query, df=df)

    if plot:
        return generate_plot_code(llm, query, schema, value_examples, df)
    else:
        return generate_result_df(llm, query, schema, value_examples, df)


@mcp_flowcept.tool()
def generate_plot_code(llm, query, dynamic_schema, value_examples, df) -> ToolResult:
    """
    Generate DataFrame and plotting code from a natural language query using an LLM.

    This tool builds a prompt with the query, dynamic schema, and example values,
    and asks the LLM to return JSON with two fields: ``result_code`` (Python code
    to transform the DataFrame) and ``plot_code`` (Python code to generate a plot).
    The resulting code is validated, executed, and the DataFrame result is
    formatted as CSV. If the LLM output is invalid JSON, the tool attempts to
    repair or extract valid JSON before failing.

    Parameters
    ----------
    llm : callable
        A language model function or wrapper that accepts a prompt string
        and returns a response.
    query : str
        Natural language query describing the desired data transformation
        and plot.
    dynamic_schema : dict
        Schema definition describing the structure of the DataFrame.
    value_examples : dict
        Example values associated with the schema to guide the LLM.
    df : pandas.DataFrame
        The DataFrame to query and transform.

    Returns
    -------
    ToolResult
        - On success (code=301): contains a dictionary with:
            - ``result_df`` : str, CSV-formatted DataFrame result.
            - ``plot_code`` : str, Python code to generate the plot.
            - ``result_code`` : str, Python code used to transform the DataFrame.
        - On failure (codes 400, 404–406, 499): contains an error message and
          optionally the original prompt for debugging.

    Raises
    ------
    Exception
        Any unhandled error during LLM invocation, JSON parsing, code execution,
        or DataFrame formatting will be caught and converted into a ``ToolResult``
        with the appropriate error code.

    Notes
    -----
    - Invalid JSON responses from the LLM are automatically retried using
      an extraction/fix helper.
    - Both transformation and plotting code must be present in the LLM output,
      otherwise the tool fails with an error.
    - Columns that contain only NaN values are dropped from the result.

    Examples
    --------
    Generate a bar chart from a sales DataFrame:

    >>> result = generate_plot_code(
    ...     llm,
    ...     query="Show total sales by region as a bar chart",
    ...     dynamic_schema=schema,
    ...     value_examples=examples,
    ...     df=sales_df
    ... )
    >>> print(result.code)
    301
    >>> print(result.result["plot_code"])
    plt.bar(result_df["region"], result_df["total_sales"])
    """
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
                return ToolResult(
                    code=405, result=f"Tried to parse this as JSON: {response}, but got Error: {e}", extra=plot_prompt
                )
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

    this_result = {"result_df": result_df, "plot_code": plot_code, "result_code": result_code}
    return ToolResult(code=301, result=this_result, tool_name=generate_plot_code.__name__)


@mcp_flowcept.tool()
def generate_result_df(llm, query: str, dynamic_schema, example_values, df, attempt_fix=True, summarize=True):
    """
    Generate a result DataFrame from a natural language query using an LLM.

    This tool constructs a prompt with the query, dynamic schema, and example values,
    then asks the LLM to generate executable pandas code. The generated code is
    executed against the provided DataFrame. If execution fails and ``attempt_fix``
    is enabled, the tool will try to repair or extract valid Python code using
    another LLM call. The resulting DataFrame is normalized, formatted, and can be
    optionally summarized.

    Parameters
    ----------
    llm : callable
        A language model function or wrapper that accepts a prompt string and
        returns a response (e.g., generated code or summary).
    query : str
        Natural language query to be executed against the DataFrame.
    dynamic_schema : dict
        Schema definition describing the structure of the DataFrame.
    example_values : dict
        Example values associated with the schema to guide the LLM.
    df : pandas.DataFrame
        The DataFrame to run the query against.
    attempt_fix : bool, default=True
        If True, attempt to fix invalid generated code by calling a repair LLM.
    summarize : bool, default=True
        If True, attempt to generate a natural language summary of the result.

    Returns
    -------
    ToolResult
        - On success (codes 301–303): contains a dictionary with:
            - ``result_code`` : str, the generated Python code.
            - ``result_df`` : str, CSV-formatted result DataFrame.
            - ``summary`` : str, summary text if generated successfully.
            - ``summary_error`` : str or None, error message if summarization failed.
        - On failure (codes 400, 405, 504): contains an error message and
          relevant debugging context.

    Raises
    ------
    Exception
        Any unhandled error during code execution, normalization, or summarization
        will be caught and converted into a ``ToolResult`` with the appropriate code.

    Notes
    -----
    - Columns with only NaN values are dropped from the result.
    - Summarization errors are non-blocking; the result DataFrame is still returned.
    - The original LLM prompt and any generated code are included in the ``extra``
      field of the ToolResult for debugging.

    Examples
    --------
    Query with valid LLM-generated code:

    >>> result = generate_result_df(
    ...     llm,
    ...     query="Show average sales by region",
    ...     dynamic_schema=schema,
    ...     example_values=examples,
    ...     df=sales_df
    ... )
    >>> print(result.code)
    301
    >>> print(result.result["result_df"])

    Handle invalid code with auto-fix disabled:

    >>> generate_result_df(llm, "bad query", schema, examples, df, attempt_fix=False)
    ToolResult(code=405, result="Failed to parse this as Python code: ...")
    """
    if llm is None:
        llm = build_llm_model()
    try:
        prompt = generate_pandas_code_prompt(query, dynamic_schema, example_values)
        response = llm(prompt)
    except Exception as e:
        return ToolResult(code=400, result=str(e), extra=prompt)

    try:
        result_code = response
        result_df = safe_execute(df, result_code)
    except Exception as e:
        if not attempt_fix:
            return ToolResult(
                code=405,
                result=f"Failed to parse this as Python code: \n\n ```python\n {result_code} \n```\n "
                f"but got error:\n\n {e}.",
                extra={"generated_code": result_code, "exception": str(e), "prompt": prompt},
            )
        else:
            tool_result = extract_or_fix_python_code(llm, result_code)
            if tool_result.code == 201:
                new_result_code = tool_result.result
                try:
                    result_df = safe_execute(df, new_result_code)
                except Exception as e:
                    return ToolResult(
                        code=405,
                        result=f"Failed to parse this as Python code: \n\n"
                        f"```python\n {result_code} \n```\n "
                        f"Then tried to LLM extract the Python code, got: \n\n "
                        f"```python\n{new_result_code}```\n "
                        f"but got error:\n\n {e}.",
                    )

            else:
                return ToolResult(
                    code=405,
                    result=f"Failed to parse this as Python code: {result_code}."
                    f"Exception: {e}\n"
                    f"Then tried to LLM extract the Python code, but got error:"
                    f" {tool_result.result}",
                )

    try:
        result_df = normalize_output(result_df)
    except Exception as e:
        return ToolResult(
            code=504,
            result="Failed to normalize output of the resulting dataframe.",
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
            )
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
        return ToolResult(
            code=405,
            result="Failed to format output of the resulting dataframe.",
            extra={"generated_code": result_code, "exception": str(e), "prompt": prompt},
        )

    this_result = {
        "result_code": result_code,
        "result_df": result_df,
        "summary": summary,
        "summary_error": summary_error,
    }
    return ToolResult(
        code=return_code, result=this_result, tool_name=generate_result_df.__name__, extra={"prompt": prompt}
    )


@mcp_flowcept.tool()
def run_df_code(user_code: str, df):
    """
    Execute user-provided Python code on a DataFrame and format the result.

    This tool safely executes Python code against a given DataFrame,
    normalizes and formats the result, and returns it as part of a
    ``ToolResult``. It is designed to let users run custom code snippets
    for data analysis while capturing errors gracefully.

    Parameters
    ----------
    user_code : str
        A string of Python code intended to operate on the provided DataFrame.
        The code must be valid and compatible with the execution environment.
    df : pandas.DataFrame
        The input DataFrame on which the code will be executed.

    Returns
    -------
    ToolResult
        - On success (code=301): a dictionary with keys:
          - ``result_code`` : str, the original code snippet.
          - ``result_df`` : str, the CSV-formatted result DataFrame.
        - On failure (code=405): the error message indicating why execution failed.

    Raises
    ------
    Exception
        Errors during execution or normalization are caught and
        converted into a ``ToolResult`` with code 405.

    Notes
    -----
    - Columns that contain only ``NaN`` values are dropped from the result.
    - If the result DataFrame is empty or not valid, an error is returned.
    - The output DataFrame is always formatted as CSV text.

    Examples
    --------
    Run a simple aggregation:

    >>> import pandas as pd
    >>> df = pd.DataFrame({"a": [1, 2, 3], "b": [10, 20, 30]})
    >>> res = run_df_code("df[['a']].sum()", df)
    >>> print(res.code)
    301
    >>> print(res.result["result_df"])
    a
    6

    Handle an invalid code snippet:

    >>> run_df_code("df.non_existing()", df)
    ToolResult(code=405, result="Failed to run this as Python code: df.non_existing(). Got error ...")
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
    result_df = format_result_df(result_df)

    this_result = {
        "result_code": user_code,
        "result_df": result_df,
    }
    return ToolResult(code=301, result=this_result, tool_name=run_df_code.__name__)


@mcp_flowcept.tool()
def extract_or_fix_python_code(llm, raw_text):
    """
    Extract or repair JSON code from raw text using an LLM.

    This tool constructs a prompt with the given raw text and passes it
    to the provided language model (LLM). The LLM is expected to either
    extract valid JSON content or repair malformed JSON from the text.
    The result is wrapped in a ``ToolResult`` object.

    Parameters
    ----------
    llm : callable
     A language model function or object that can be invoked with a
     prompt string and returns a response (e.g., an LLM wrapper).
    raw_text : str
     The raw text containing JSON code or fragments that may need to
     be extracted or fixed.

    Returns
    -------
    ToolResult
     A result object containing:
     - ``code=201`` if the extraction/fix succeeded, with the LLM
       output in ``result``.
     - ``code=499`` if an exception occurred, with the error message
       in ``result``.

    Raises
    ------
    Exception
     Any unhandled exception from the LLM call will be caught and
     returned as part of the ``ToolResult``.

    Examples
    --------
    >>> # Example with a mock LLM that just echoes back
    >>> def mock_llm(prompt):
    ...     return '{"a": 1, "b": 2}'
    >>> res = extract_or_fix_json_code(mock_llm, "Here is some JSON: {a:1, b:2}")
    >>> print(res)
    ToolResult(code=201, result='{"a": 1, "b": 2}')

    Example with an invalid call:

    >>> def broken_llm(prompt):
    ...     raise RuntimeError("LLM service unavailable")
    >>> res = extract_or_fix_json_code(broken_llm, "{a:1}")
    >>> print(res)
    ToolResult(code=499, result='LLM service unavailable')
    """
    prompt = extract_or_fix_python_code_prompt(raw_text)
    try:
        response = llm(prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def extract_or_fix_json_code(llm, raw_text) -> ToolResult:
    """
    Extract or repair JSON code from raw text using a language model.

    This function builds a prompt around the provided raw text and sends
    it to the given language model (LLM). The LLM is expected to extract
    valid JSON or attempt to fix malformed JSON structures. The outcome
    is returned in a ``ToolResult`` object, with a success or error code.

    Parameters
    ----------
    llm : Callable[[str], str]
        A callable LLM function or wrapper that accepts a prompt string
        and returns a string response.
    raw_text : str
        Input text that contains JSON code or fragments that may be
        incomplete or malformed.

    Returns
    -------
    ToolResult
        A result object with:
        - ``code=201`` and the LLM response in ``result`` if successful.
        - ``code=499`` and the error message in ``result`` if an error occurs.

    Examples
    --------
    Successful extraction/fix:

    >>> def mock_llm(prompt: str) -> str:
    ...     return '{"foo": "bar"}'
    >>> extract_or_fix_json_code(mock_llm, "Broken JSON: {foo: bar}")
    ToolResult(code=201, result='{"foo": "bar"}')

    Error handling:

    >>> def broken_llm(prompt: str) -> str:
    ...     raise RuntimeError("LLM not available")
    >>> extract_or_fix_json_code(broken_llm, "{foo: bar}")
    ToolResult(code=499, result='LLM not available')
    """
    prompt = extract_or_fix_json_code_prompt(raw_text)
    try:
        response = llm(prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=499, result=str(e))


@mcp_flowcept.tool()
def summarize_result(
    llm,
    code,
    result,
    query: str,
    dynamic_schema,
    example_values,
) -> ToolResult:
    """
    Summarize the pandas result with local reduction for large DataFrames.
    - For wide DataFrames, selects top columns based on variance and uniqueness.
    - For long DataFrames, truncates to preview rows.
    - Constructs a detailed prompt for the LLM with original column context.
    """
    summarized_df = summarize_df(result, code)
    prompt = dataframe_summarizer_context(code, summarized_df, dynamic_schema, example_values, query)
    try:
        response = llm(prompt)
        return ToolResult(code=201, result=response)
    except Exception as e:
        return ToolResult(code=400, result=str(e))


@mcp_flowcept.tool()
def save_df(df, schema, value_examples):
    """
    Save a DataFrame, its schema, and example values to temporary files.

    This function writes the provided DataFrame, schema, and value
    examples to the ``/tmp`` directory. The schema and value examples
    are saved as JSON files, while the DataFrame is saved as a CSV
    file. This can be useful for persisting the current state of an
    agent's task data for later querying or debugging.

    Parameters
    ----------
    df : pandas.DataFrame
        The DataFrame to save.
    schema : dict
        A dictionary describing the schema of the DataFrame.
    value_examples : dict
        Example values associated with the DataFrame schema.

    Returns
    -------
    ToolResult
        An object with a status code and result message confirming
        successful persistence of the data.

    Notes
    -----
    Files are written to fixed locations in ``/tmp``:

    - ``/tmp/current_tasks_schema.json`` — schema
    - ``/tmp/value_examples.json`` — example values
    - ``/tmp/current_agent_df.csv`` — DataFrame contents

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({"name": ["Alice", "Bob"], "score": [85, 92]})
    >>> schema = {"fields": [{"name": "name", "type": "string"},
    ...                      {"name": "score", "type": "integer"}]}
    >>> examples = {"name": ["Alice"], "score": [85]}
    >>> result = save_df(df, schema, examples)
    >>> print(result)
    ToolResult(code=201, result='Saved df and schema to /tmp directory')
    """
    with open("/tmp/current_tasks_schema.json", "w") as f:
        json.dump(schema, f, indent=2)
    with open("/tmp/value_examples.json", "w") as f:
        json.dump(value_examples, f, indent=2)
    df.to_csv("/tmp/current_agent_df.csv", index=False)
    return ToolResult(code=201, result="Saved df and schema to /tmp directory")


@mcp_flowcept.tool()
def query_on_saved_df(query: str, dynamic_schema_path, value_examples_path, df_path):
    """
    Run a natural language query against a saved DataFrame with schema and value examples.

    This function loads a previously saved DataFrame, dynamic schema,
    and value examples from disk, then uses a language model (LLM) to
    interpret the query and generate a new result DataFrame. The query
    is executed through the LLM using the provided schema and examples
    for better accuracy.

    Parameters
    ----------
    query : str
        Natural language query to execute against the DataFrame.
    dynamic_schema_path : str
        Path to a JSON file containing the schema definition used by the LLM.
    value_examples_path : str
        Path to a JSON file with example values to guide the LLM query.
    df_path : str
        Path to the saved DataFrame file.

    Returns
    -------
    pandas.DataFrame
        The DataFrame result generated by the LLM query.

    Raises
    ------
    FileNotFoundError
        If any of the provided paths (schema, examples, DataFrame) do not exist.
    json.JSONDecodeError
        If schema or examples JSON files cannot be parsed.
    Exception
        Propagates exceptions from the LLM query or DataFrame loading.

    Examples
    --------
    Query a saved DataFrame of sales data:

    >>> query = "Show me the total sales by region"
    >>> result = query_on_saved_df(
    ...     query,
    ...     dynamic_schema_path="schemas/sales_schema.json",
    ...     value_examples_path="schemas/sales_examples.json",
    ...     df_path="data/sales.parquet"
    ... )
    >>> print(result.head())
       region   total_sales
    0   North         12345
    1   South          9876
    2    West          5432
    """
    df = load_saved_df(df_path)

    with open(dynamic_schema_path) as f:
        dynamic_schema = json.load(f)

    with open(value_examples_path) as f:
        value_examples = json.load(f)

    llm = build_llm_model()
    return generate_result_df(llm, query, dynamic_schema, value_examples, df, attempt_fix=False, summarize=False)
