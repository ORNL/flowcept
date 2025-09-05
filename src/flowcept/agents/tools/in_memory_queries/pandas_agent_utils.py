import json
import re
import pandas as pd
import numpy as np
import ast


def load_saved_df(df_path: str) -> pd.DataFrame:
    """
    Load a DataFrame from a CSV file.

    Parameters
    ----------
    df_path : str
        Path to the CSV file containing the DataFrame.

    Returns
    -------
    pd.DataFrame
        The loaded DataFrame.
    """
    df = pd.read_csv(df_path, index_col=False)
    str_types = ["task_id", "parent_task_id", "workflow_id", "activity_id", "agent_id", "campaign_id", "hostname"]
    for col in str_types:
        if col in df.columns:
            df[col] = df[col].astype(str)
    dates = ["started_at", "ended_at"]
    for date in dates:
        if date in df.columns:
            df[date] = pd.to_datetime(df[date], errors="coerce")
    return df


def normalize_output(result):
    """
    Ensures the result is returned as a pandas DataFrame.
    Converts scalars to 1-row, 1-col DataFrame, Series to 1-row DataFrame,
    and supports lists, NumPy arrays, and NumPy scalars.

    Parameters
    ----------
    result : Any
        The result from code execution (can be DataFrame, Series, scalar, list, or array).

    Returns
    -------
    pd.DataFrame
        A well-formatted DataFrame representation of the result.
    """
    if result is None:
        raise Exception("Result Data Frame is Empty.")

    _df: pd.DataFrame = None
    if isinstance(result, pd.DataFrame):
        _df = result

    elif isinstance(result, pd.Series):
        # Convert Series to single-row DataFrame
        _df = pd.DataFrame([result])

    elif isinstance(result, (int, float, str, bool, np.generic)):
        # Scalars or numpy scalars
        _df = pd.DataFrame({"Scalar_Value": [result]})

    elif isinstance(result, (list, tuple)):
        _df = pd.DataFrame({"List_Value": result})

    elif isinstance(result, np.ndarray):
        if result.ndim == 1:
            _df = pd.DataFrame({"Array_Value": result})
        elif result.ndim == 2:
            _df = pd.DataFrame(result)
        else:
            raise ValueError(f"Unsupported ndarray shape: {result.shape}")

    else:
        raise TypeError(f"Unsupported result type: {type(result)}")

    if not len(_df):
        raise ValueError("Result DataFrame is Empty.")

    return _df


def safe_execute(df: pd.DataFrame, code: str):
    """
    Strip any leftover fences, then execute the code in a limited namespace.
    Returns result or None.
    """
    code = clean_code(code)
    local_env = {"df": df, "pd": pd, "np": np}
    exec(code, {}, local_env)
    return local_env.get("result", None)


def format_result_df(result_df) -> str:
    """
    Format a pandas DataFrame as a CSV string with safety checks.

    This function validates that the input is a pandas DataFrame,
    ensures it is not empty, and converts it to a CSV string. If the
    DataFrame is very large, only the first 100 rows are included.

    Parameters
    ----------
    result_df : pandas.DataFrame
        The DataFrame to format.

    Returns
    -------
    str
        A CSV-formatted string representation of the DataFrame.

    Raises
    ------
    Exception
        If the input is not a DataFrame or if the DataFrame is empty.

    Notes
    -----
    - The maximum number of rows returned is 100. If the DataFrame has
      more than 100 rows, a message is printed and only the first 100
      rows are included.
    - The index column is omitted in the CSV output.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    >>> print(format_result_df(df))
    a,b
    1,x
    2,y
    3,z

    Example with more than 100 rows:

    >>> df = pd.DataFrame({"col": range(200)})
    >>> csv_str = format_result_df(df)  # prints warning
    >>> len(csv_str.splitlines())  # 101 lines (header + 100 rows)
    101
    """
    if isinstance(result_df, pd.DataFrame):
        if not len(result_df):
            raise Exception("Empty DataFrame")
        if len(result_df) > 100:
            print("Result set is too long. We are only going to send the head.")  # TODO log
            # TODO deal with very long results later
            result_df = result_df.head(100)
        result_df = result_df.to_csv(index=False)
        return result_df
    else:
        raise Exception("Not a valid DataFrame")


def safe_json_parse(text):
    r"""
    Safely parse a string into a JSON object with minimal error recovery.

    This function attempts to parse the given text as JSON. If the
    initial parsing fails, it tries to fix common issues such as:

    - Leading/trailing whitespace
    - Surrounding backticks (e.g., Markdown-formatted JSON)
    - Missing opening/closing braces

    Parameters
    ----------
    text : str
        The input string expected to contain JSON content.

    Returns
    -------
    object
        The Python object resulting from parsing the JSON string
        (usually a dict or list).

    Raises
    ------
    ValueError
        If the text cannot be parsed as valid JSON even after recovery attempts.

    Examples
    --------
    Valid JSON string:

    >>> safe_json_parse('{"a": 1, "b": 2}')
    {'a': 1, 'b': 2}

    With backticks and whitespace:

    >>> safe_json_parse("``` { \\"x\\": 42 } ```")
    {'x': 42}

    Missing braces:

    >>> safe_json_parse('"y": 99')
    {'y': 99}
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to fix common issues
        text = text.strip().strip("`")  # remove backticks or whitespace
        if not text.startswith("{"):
            text = "{" + text
        if not text.endswith("}"):
            text = text + "}"
        try:
            return json.loads(text)
        except Exception as e:
            raise ValueError(f"Still failed to parse JSON: {e}")


def clean_code(text):
    """
    Extracts the first valid Python code block or line that starts with 'result =' from a model response.

    Parameters
    ----------
    text : str
        The raw string response from the agent.

    Returns
    -------
    str
        The extracted Python code or an empty string if none found.
    """
    # Try to find code block with triple backticks first
    block_match = re.search(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
    if block_match:
        return block_match.group(1).strip()

    # Fallback: try to find a line that starts with "result ="
    line_match = re.search(r"(result\s*=\s*.+)", text)
    if line_match:
        return line_match.group(1).strip()

    return ""


def summarize_df(df: pd.DataFrame, df_query_code: str, max_rows: int = 5, max_cols: int = 10) -> pd.DataFrame:
    """
    Given a DataFrame and query code string that operates on it, return a reduced version
    of the DataFrame that includes only the used columns and a small number of rows,
    but only if the DataFrame exceeds the row or column limits.

    Parameters
    ----------
    df : pd.DataFrame
        The full DataFrame.
    df_query_code : str
        The string containing Python code that operates on the DataFrame `df`.
    max_rows : int, optional
        Maximum number of rows to include in the reduced DataFrame (default is 5).
    max_cols : int, optional
        Maximum number of columns to include (default is 10).

    Returns
    -------
    pd.DataFrame
        A reduced version of the DataFrame suitable for sending to an LLM.
    """

    def extract_columns_from_code(code: str) -> list:
        """Extract column names accessed via df[...] or df.<column> in the code string."""
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return []

        columns = set()

        class ColumnVisitor(ast.NodeVisitor):
            def visit_Subscript(self, node):
                if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str):
                    columns.add(node.slice.value)
                elif isinstance(node.slice, ast.Index) and isinstance(node.slice.value, ast.Str):
                    columns.add(node.slice.value.s)
                self.generic_visit(node)

            def visit_Attribute(self, node):
                columns.add(node.attr)
                self.generic_visit(node)

        ColumnVisitor().visit(tree)

        string_accesses = re.findall(r'\[["\']([\w\.\-]+)["\']\]', code)
        columns.update(string_accesses)

        return list(columns)

    used_columns = extract_columns_from_code(df_query_code)
    relevant_cols = [col for col in used_columns if col in df.columns]

    if not relevant_cols:
        relevant_cols = list(df.columns)

    # Only apply column reduction if column count exceeds max_cols
    if len(relevant_cols) > max_cols:
        relevant_cols = relevant_cols[:max_cols]

    reduced_df = df[relevant_cols]

    # Only apply row reduction if row count exceeds max_rows
    if reduced_df.shape[0] > max_rows:
        reduced_df = reduced_df.sample(n=max_rows, random_state=42)

    return reduced_df.reset_index(drop=True)
