import json


import re
import textwrap
from flowcept.agents.agents_utils import build_llm_model
from flowcept.agents.prompts.in_memory_query_prompts import dataframe_summarizer_context, COMMON_TASK_FIELDS, \
    generate_plot_code_prompt

import pandas as pd
import numpy as np

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
        _df = pd.DataFrame({'Scalar_Value': [result]})

    elif isinstance(result, (list, tuple)):
        _df = pd.DataFrame({'List_Value': result})

    elif isinstance(result, np.ndarray):
        if result.ndim == 1:
            _df = pd.DataFrame({'Array_Value': result})
        elif result.ndim == 2:
            _df = pd.DataFrame(result)
        else:
            raise ValueError(f"Unsupported ndarray shape: {result.shape}")

    else:
        raise TypeError(f"Unsupported result type: {type(result)}")

    if not len(_df):
        raise ValueError(f"Result DataFrame is Empty.")

    return _df
def safe_execute(df: pd.DataFrame, code: str):
    """
    Strip any leftover fences, then execute the code in a limited namespace.
    Returns result or None
    """
    code = clean_code(code)
    local_env = {"df": df, "pd": pd, "np": np}
    exec(code, {}, local_env)
    return local_env.get("result", None)


def format_result_df(result_df) -> str:
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
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to fix common issues
        text = text.strip().strip('`')  # remove backticks or whitespace
        if not text.startswith('{'):
            text = '{' + text
        if not text.endswith('}'):
            text = text + '}'
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
