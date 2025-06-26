import json
import re
from typing import Tuple

import textwrap
from flowcept.agents.agents_utils import build_llm_model, count_tokens, tuples_to_langchain_messages, \
    flatten_prompt_messages

# ------------------ LLM Setup ------------------
llm = build_llm_model()


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
        return None
    if isinstance(result, pd.DataFrame):
        return result

    elif isinstance(result, pd.Series):
        # Convert Series to single-row DataFrame
        return pd.DataFrame([result])

    elif isinstance(result, (int, float, str, bool, np.generic)):
        # Scalars or numpy scalars
        return pd.DataFrame({'Scalar_Value': [result]})

    elif isinstance(result, (list, tuple)):
        return pd.DataFrame({'List_Value': result})

    elif isinstance(result, np.ndarray):
        if result.ndim == 1:
            return pd.DataFrame({'Array_Value': result})
        elif result.ndim == 2:
            return pd.DataFrame(result)
        else:
            raise ValueError(f"Unsupported ndarray shape: {result.shape}")

    else:
        raise TypeError(f"Unsupported result type: {type(result)}")


def summarize_result(code, result, original_cols: list[str], query: str) -> str:
    """
    Summarize the pandas result with local reduction for large DataFrames.
    - For wide DataFrames, selects top columns based on variance and uniqueness.
    - For long DataFrames, truncates to preview rows.
    - Constructs a detailed prompt for the LLM with original column context.
    """
    # Handle DataFrame results
    if isinstance(result, pd.DataFrame):
        df = result.copy()
        summary_reason = ""
        MAX_COLS = 10
        MAX_ROWS = 5

        if df.shape[1] > MAX_COLS:
            numeric_cols = df.select_dtypes(include=[np.number])
            non_numeric_cols = df.select_dtypes(exclude=[np.number])

            top_var_cols = (
                numeric_cols.var()
                .sort_values(ascending=False)
                .head(MAX_COLS // 2)
                .index.tolist()
            )

            top_cat_cols = (
                non_numeric_cols.nunique()
                .sort_values(ascending=False)
                .head(MAX_COLS - len(top_var_cols))
                .index.tolist()
            )

            selected_cols = top_var_cols + top_cat_cols
            df = df[selected_cols]
            summary_reason = (
                f"(Top {len(top_var_cols)} numeric columns by variance and "
                f"{len(top_cat_cols)} categorical columns by uniqueness.)"
            )
            summary_reason = f"Summary reason: {summary_reason}"

        # Preview rows
        if len(df) > MAX_ROWS:
            preview = pd.concat([
                df.head(),
                pd.DataFrame([["..."] * df.shape[1]], columns=df.columns)
            ], ignore_index=True)
        else:
            preview = df

        summary_text = preview.to_string(index=False)
        cols_str = ", ".join(original_cols)
        prompt = (
            f"You are a Workflow Provenance Specialist analyzing a DataFrame that was generated to answer a user query."
            f"This DataFrame is the result of the execution of the following code:\n"
            f"{code}\n"
            f"where the original DataFrame `df` had these columns: {cols_str}.\n"
            f"{summary_reason}\n"
            f"Result DataFrame:\n{summary_text}\n"
            f"Given this result, create a concise answer to the following user query: {query}."
            f"BE CONCISE!"
        )
        return llm(prompt)



def fix_code(original_prompt, original_code, error):
    prompt = (f"You are a Data Scientist expert debugging a Pandas DataFrame error that appeared when running the following code:"
              f"{original_code}"
              f"When this code ran, we got this error: {error}"
              f"Now, please fix this error"
              f"Only provide the code block without any markdown fences or explanation.")
    response = llm(prompt)
    # Extract code inside ```python ... ```
    match = re.search(r"```(?:python)?\s*(.*?)\s*```", response, re.DOTALL)
    code = match.group(1) if match else response
    return textwrap.dedent(code).strip()

# def generate_pandas_code(df: pd.DataFrame, query: str) -> Tuple[str, str]:
#     """
#     Use the LLM to generate pandas code for a user query.
#     Strips any markdown fences and returns clean Python code.
#     """
#     schema = ", ".join(df.columns)
#     examples_prompt = "\n\n".join(
#         f"### Example\nQuestion: {ex['question']}\nCode:\n```python\n{ex['code']}\n```"
#         for ex in FEW_SHOT_EXAMPLES
#     )
#     prompt = f"""
# You are an Workflow Provenance Expert with high data science skills in Pandas DataFrame analytics, translating natural language queries into pandas code.
# The DataFrame 'df' contains data about tasks that ran in a workflow execution. It has columns: {schema}. Here are descriptions about the fields:
# - If user is giving names or kinds or classes to tasks or activities, of if user is namely qualifying tasks, use the column 'activity_id' to filter tasks;
# - hostname has the compute node name where the task was executed. Use it for scheduling-related queries or when user wants to know where the tasks ran.
# - If user asks about 'input' or 'used' values or variables or parameters, consider all columns that begin with 'used.<field>'; Examples of input fields are: 'used.layers'.
# - If user asks about 'output' or 'generated' variables or results, consider all columns that begin with 'generated.<field>'; Examples of generated fields are: 'generated.loss'
# - All columns that begin with 'telemetry_summary.' are related to resource consumption.
# - If the user queries that are related to task duration, task lasting (e.g., short or long-lasting), use the column  telemetry_summary.duration_sec.;
# - Queries related to outliers are worth looking at the column tags, unless the user explicitly asks not to use it. The tag column is a stringfied list where critical tasks are tagged. If the row is not a critical task, this column is null.;
# - If user queries involve agents', select the rows that has non-empty or non-null 'agent_id' column;
# - Unless explicitly asked, avoid using .dropna() to remove rows that has at least one NaN value in any column.
# - When accessing used.* fields or generated.* fields, you need to access them as df.columns[df.columns.str.startswith('used.')] or as df.columns[df.columns.str.startswith('generated.')]
# Generate Python pandas code to assign the answer to a variable named 'result'.
# Feel free to chain multiple pandas df operations if needed, as long as the resulting df is in the 'result' variable.
# Only provide the code block without any markdown fences or explanation.
#
# {examples_prompt}
#
# ### User Query
# Question: {query}
# Code:
# """
#     # TODO add more info about the schema (metaschema).
#     response = llm(prompt)
#     # Extract code inside ```python ... ```
#     match = re.search(r"```(?:python)?\s*(.*?)\s*```", response, re.DOTALL)
#     code = match.group(1) if match else response
#     return prompt, textwrap.dedent(code).strip()


def generate_pandas_code2(query: str, dynamic_schema):
    PROMPT_TEMPLATE = f"""
    You are a Workflow Provenance Data Science Expert working with a flattened pandas DataFrame named `df`, created using `pd.json_normalize(tasks)`.

    ## DATAFRAME STRUCTURE

    Each row in `df` represents a single task.

    ### 1. Structured task fields:

    - **in**: input parameters (columns starting with `used.`)
    - **out**: output metrics/results (columns starting with `generated.`)
    - **tel**: telemetry (columns starting with `telemetry_summary.`)

    The schema for these fields is defined in the `schema` dictionary below. Each key is an `activity_id` representing a task type, and the value lists the available fields:

    {dynamic_schema}

    Each field has:
    - `n`: full column name
    - `d`: data type (`int`, `float`, `str`, `bool`, or `list`)
    - `v`: sample values

    Use this schema to understand what inputs and outputs are valid for each activity.

    ### 2. Additional fields for tasks 

    | Column                        | Description |
    |-------------------------------|-------------|
    | `workflow_id`                 | Workflow the task belongs to |
    | `task_id`                     | Unique identifier |
    | `activity_id`                 | Type of task (e.g., 'choose_option') |
    | `campaign_id`                 | Task group |
    | `hostname`                    | Compute node name |
    | `agent_id`                    | Set if executed by an agent |
    | `started_at`                  | Start time |
    | `tags`                        | List of descriptive tags |
    | `telemetry_summary.duration_sec` | Task duration (seconds) |

    ### 3. Query Interpretation Guidelines

    - Use `df` as the base DataFrame.
    - Use `activity_id` to filter by task type (valid values = schema keys).
    - Use `used.` for parameters (inputs) and `generated.` for outputs (metrics).
    - Use `telemetry_summary.duration_sec` for performance-related questions.
    - Use `hostname` when user mentions *where* a task ran.
    - Use `agent_id` when the user refers to agents (non-null means task was agent-run).

    ### 4. Hard Constraints (obey strictly)

    - Always return code in the form `result = df[<filter>][[...]]` or `result = df.loc[<filter>, [...]]`
    - Always drop columns that are entirely null in the final result by appending `.dropna(axis=1, how='all')` at the end of the query.
    - **When filtering by `activity_id`, only select columns that belong to that activity’s schema.**
        - Use only `used.` and `generated.` fields listed in the schema for that `activity_id`.
        - Explicitly list the selected columns — **never return all columns**
    - **Only include telemetry columns if used in the query logic.**
    - **Do not include metadata columns unless explicitly required by the user query.**

    ### 5. Few-Shot Examples

    # Q: How many tasks were processed?
    result = len(df))

    # Q: How many tasks for each activity?
    result = df['activity_id'].value_counts()

    # Q: What is the average loss across all tasks?
    result = df['generated.loss'].mean()

    # Q: select the 'choose_option' tasks executed by the agent, and show the planned controls, generated option, scores, explanations
    result = df[(df['activity_id'] == 'choose_option') & (df['agent_id'].notna())][['used.planned_controls', 'generated.option', 'used.scores.scores', 'generated.explanation']].copy()
    
    # Q: Show duration and generated scores for 'simulate_layer' tasks
    result = df[df['activity_id'] == 'simulate_layer'][['telemetry_summary.duration_sec', 'generated.scores']]
    
    6. Final Instructions
    Return only valid pandas code assigned to the variable result.

    Your response must be only the raw Python code in the format:
        result = ...
    
    Do not include: Explanations, Markdown, Comments, Any text before or after the code block
    
    Your entire output must be only one line or block of valid Python code, without wrapping it in triple backticks or quotes.

    Strictly follow the constraints above.

    User Query:
    {query}
    """

    try:
        #estimated_tokens = count_tokens(PROMPT_TEMPLATE)
        #max_tokens = 8192 - estimated_tokens
        #_llm = build_llm_model(model_kwargs={"max_tokens": max_tokens}) # hack to avoid llama models max tokens issues
        #response = _llm(PROMPT_TEMPLATE)
        response = llm(PROMPT_TEMPLATE)
        return PROMPT_TEMPLATE, response, True
    except Exception as e:
        return PROMPT_TEMPLATE, str(e), False



# def clean_code(code):
#     # Clean fences
#     code = re.sub(r"^```(?:python)?", "", code, flags=re.MULTILINE)
#     code = code.replace("```", "")
#     code = textwrap.dedent(code)
#     return code

def safe_execute(df: pd.DataFrame, code: str):
    """
    Strip any leftover fences, then execute the code in a limited namespace.
    Returns (result, error).
    """
    code = clean_code(code)
    local_env = {"df": df, "pd": pd, "np": np}
    try:
        exec(code, {}, local_env)
        return local_env.get("result", None), None
    except Exception as e:
        return None, str(e)



def generate_plot_code(query, dynamic_schema):
    PLOT_PROMPT = f"""
    You are a Streamlit chart expert. The user has a pandas DataFrame called `df`, created from flattened task objects using `pd.json_normalize`.

    ## DATAFRAME STRUCTURE

    Each row in `df` represents a single task.

    ### 1. Structured task fields:

    - **in**: input parameters (columns starting with `used.`)
    - **out**: output metrics/results (columns starting with `generated.`)
    - **tel**: telemetry (columns starting with `telemetry_summary.`)

    The schema for these fields is defined in the `schema` dictionary below. Each key is an `activity_id` representing a task type, and the value lists the available fields:

    {dynamic_schema}

    Each field has:
    - `n`: full column name
    - `d`: data type (`int`, `float`, `str`, `bool`, or `list`)
    - `v`: sample values

    Use this schema to understand what inputs and outputs are valid for each activity.

    ### 2. Additional fields for tasks 

    | Column                        | Description |
    |-------------------------------|-------------|
    | `workflow_id`                 | Workflow the task belongs to |
    | `task_id`                     | Unique identifier |
    | `activity_id`                 | Type of task (e.g., 'choose_option') |
    | `campaign_id`                 | Task group |
    | `hostname`                    | Compute node name |
    | `agent_id`                    | Set if executed by an agent |
    | `started_at`                  | Start time |
    | `tags`                        | List of descriptive tags |
    | `telemetry_summary.duration_sec` | Task duration (seconds) |

    ---
    ### 3. Guidelines
    
    - When plotting from a grouped or aggregated result, set an appropriate column (like activity_id, started_at, etc.) as the index before plotting to ensure x-axis labels are correct.
    
    ### 4. Output Format

    You must write Python code using Streamlit (st) to visualize the requested data.

    - Always assume `df` is already defined.
    - First, assign the query result to a variable called `result` using pandas.
    - Then, write the plotting code based on `result`.
    - Return a Python dictionary with two fields:
      - `"result_code"`: the pandas code that assigns `result`
      - `"plot_code"`: the code that creates the Streamlit plot
    ---

    ### 5. Few-Shot Examples

    ```python
    # Q: Plot the number of tasks by activity
    {{
    "result_code": "result = df['activity_id'].value_counts().reset_index().rename(columns={{'index': 'activity_id', 'activity_id': 'count'}})",
      "plot_code": "st.bar_chart(result.set_index('activity_id'))"
    }}

    # Q: Show a line chart of task duration per task start time
    {{
    "result_code": "result = df[['started_at', 'telemetry_summary.duration_sec']].dropna().set_index('started_at')",
      "plot_code": "st.line_chart(result)"
    }}

    # Q: Plot average scores for simulate_layer tasks
    {{
    "result_code": "result = df[df['activity_id'] == 'simulate_layer'][['generated.scores']].copy()\nresult['avg_score'] = result['generated.scores'].apply(lambda x: sum(eval(str(x))) / len(eval(str(x))) if x else 0)",
      "plot_code": "st.bar_chart(result['avg_score'])"
    }}

    # Q: Plot histogram of planned controls count for choose_option
    {{
    "result_code": "result = df[df['activity_id'] == 'choose_option'][['used.planned_controls']].copy()\nresult['n_controls'] = result['used.planned_controls'].apply(lambda x: len(eval(str(x))) if x else 0)",
      "plot_code": "import matplotlib.pyplot as plt\nplt.hist(result['n_controls'])\nst.pyplot(plt)"
    }}
    
    User request:
    {query}
    
    Do not include markdown, code fences, or any comments. ONLY GENERATE A VALID JSON WITH TWO KEYS.

"""
    llm = build_llm_model()
    try:
        response = llm(PLOT_PROMPT)
        #response = clean_code(response)
        result = safe_json_parse(response)
        #estimated_tokens = count_tokens(PROMPT_TEMPLATE)
        #max_tokens = 8192 - estimated_tokens
        #_llm = build_llm_model(model_kwargs={"max_tokens": max_tokens}) # hack to avoid llama models max tokens issues
        #response = _llm(PROMPT_TEMPLATE)
        return PLOT_PROMPT, result, True
    except Exception as e:
        return PLOT_PROMPT, str(e), False

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

def exec_st_plot_code(code, result_df, st_module):
    try:
        code = clean_code(code)
        print("Code\n",code)
        exec(code, {'result': result_df, 'st': st_module, 'plt': __import__('matplotlib.pyplot'), 'alt': __import__('altair')})
    except Exception as e:
        st_module.error(f"Plot execution error: {e}")



# def condense_schema(schema_dict: dict[str, dict[str, list[dict]]]) -> tuple[str, str]:
#     """
#     Returns:
#     --------
#     - schema_str: compact one-liner per task
#     - explanation: minimal format guide for LLM
#     """
#     lines = []
#     for activity, sections in schema_dict.items():
#         fields = []
#         for section_key in ("in", "out", "tel"):
#             for f in sections.get(section_key, []):
#                 name = f.get("n", "")
#                 dtype = f.get("d", "")
#                 values = f.get("v", [])
#                 short_vals = values[:2] if isinstance(values, list) else [values]
#                 fields.append(f"{section_key}.{name}:{dtype}={short_vals}")
#         lines.append(f"{activity}=" + ",".join(fields))
#
#     schema_str = "\n".join(lines)
#
#     explanation = (
#         "Each line: task_name=field:type=[sample_values],...\n"
#         "field starts with in., out., or tel. for input, output, telemetry.\n"
#         "Types are int, float, str, bool, list. Sample values show typical data."
#     )
#
#     return schema_str, explanation
#
#
COMMON_FIELDS = {
    "workflow_id": "workflow the task belongs to",
    "task_id": "unique task ID",
    "activity_id": "task type (e.g. choose_option)",
    "campaign_id": "task group ID",
    "hostname": "compute node",
    "agent_id": "set if run by agent",
    "started_at": "start time",
    "tags": "list of tags",
    "telemetry_summary.duration_sec": "task duration (sec)"
}
#
# def condense_common_task_schema(column_dict: dict[str, str] = COLUMN_DESCRIPTIONS) -> tuple[str, str]:
#     """
#     Returns:
#     - condensed_str: One-liner in format col=desc; ...
#     - explanation: Minimal guide for LLMs to interpret it
#     """
#     condensed_str = "; ".join(f"{col}={desc}" for col, desc in column_dict.items())
#
#     explanation = (
#         "Format: col=desc; ... Each pair maps a column to its meaning."
#     )
#
#     return condensed_str, explanation
#
#
# STATIC_SCHEMA = condense_common_task_schema()
#


# #### DATA FRAMES
# INTERPRETATION_GUIDELINES = [
#     "Use df as the base DataFrame.",
#     "Filter tasks using df['activity_id'] == <task_type>.",
#     "Inputs use 'used.', outputs use 'generated.'.",
#     "Use 'telemetry_summary.duration_sec' for performance.",
#     "Use 'hostname' when asking where a task ran.",
#     "Use 'agent_id' when referring to agent-executed tasks (non-null)."
# ]

# HARD_CONSTRAINTS = [
#     "Always return: result = df[<filter>][[...]] or df.loc[<filter>, [...]]",
#     "Append .dropna(axis=1, how='all') to drop all-null columns.",
#     "When filtering by activity_id, only include columns from that activity’s schema.",
#     "Only use 'used.' and 'generated.' fields listed in the schema.",
#     "Explicitly list columns — never use all.",
#     "Include telemetry columns only if used in logic.",
#     "Do not include metadata unless explicitly requested.",
# ]
#
# FEW_SHOT_EXAMPLES = [
#     {
#         "query": "How many tasks were run for each activity?",
#         "code": "result = df['activity_id'].value_counts()"
#     },
#     {
#         "query": "What is the average loss across all tasks?",
#         "code": "result = df['generated.loss'].mean()"
#     },
#     {
#         "query": "Select 'choose_option' tasks run by agents and show planned controls, option, scores, explanation.",
#         "code": "result = df[(df['activity_id'] == 'choose_option') & (df['agent_id'].notna())][['used.planned_controls', 'generated.option', 'used.scores.scores', 'generated.explanation']].copy()"
#     },
#     {
#         "query": "Show duration and generated scores for 'simulate_layer' tasks.",
#         "code": "result = df[df['activity_id'] == 'simulate_layer'][['telemetry_summary.duration_sec', 'generated.scores']]"
#     }
# ]
# OUTPUT_CONSTRAINTS = [
#     "Return only valid pandas code assigned to the variable result.",
#     "DO NOT include any explanation, markdown, or extra output."
# ]


# def generate_pandas_code3(query, dynamic_schema):
#     messages = build_df_query_prompt_messages(query, dynamic_schema)
#
#     flatten_msg = ""
#     for m in messages:
#         if len(m):
#             flatten_msg += m[1] + "\n"
#         else:
#             flatten_msg += "\n"
#
#     try:
#         response = llm.invoke(flatten_msg)
#         return messages, response, True
#     except Exception as e:
#         return messages, str(e), False

# def build_df_query_prompt_messages(
#     query: str,
#     dynamic_schema: tuple[str, str],
#     static_schema: tuple[str, str] = STATIC_SCHEMA,
#     interpretation_guidelines: list[str] = INTERPRETATION_GUIDELINES,
#     hard_constraints: list[str] = HARD_CONSTRAINTS,
#     few_shot_examples: list[dict] = FEW_SHOT_EXAMPLES
# ) -> list[tuple[str, str]]:
#     """
#     Assembles the message list for LLM prompt injection, mixing schema, constraints,
#     few-shot examples, and final query.
#
#     Returns
#     -------
#     list of (role, content)
#         Tuples where role ∈ {"system", "user", "assistant"}
#     """
#     condensed_dynamic_schema = dynamic_schema[0]
#     condensed_dynamic_schema_format_explanation = dynamic_schema[1]
#     static_condensed_schema = static_schema[0]
#     condensed_static_schema_format_explanation = static_schema[1]
#
#     messages: list[tuple[str, str]] = []
#
#     # System message with schema and rules
#     system_parts = [
#         "You are a Workflow Provenance Data Science Expert working with a flattened pandas DataFrame named `df`, created using `pd.json_normalize(tasks)`.",
#         "",
#         "### 1. DATAFRAME STRUCTURE",
#         "Each row in `df` represents a single task.",
#         "",
#         "#### 1. Structured task fields by activity_id:",
#         condensed_dynamic_schema_format_explanation,
#         condensed_dynamic_schema,
#         "",
#         "#### 2. Common task fields (shared across all tasks):",
#         condensed_static_schema_format_explanation,
#         static_condensed_schema,
#         "",
#         "### 2. QUERY INTERPRETATION GUIDELINES",
#         *[f"- {g}" for g in interpretation_guidelines],
#         "",
#         "### 3. HARD CONSTRAINTS (STRICTLY ENFORCED)",
#         *[f"- {c}" for c in hard_constraints]
#     ]
#     messages.append(("system", "\n".join(system_parts)))
#
#     messages.append(("system", "### 4. Few-shot examples:"))
#     for example in few_shot_examples:
#         question = example.get("query", "").strip()
#         code = example.get("code", "").strip()
#         if question and code:
#             messages.extend([
#                 ("user", f"Q: {question}"),
#                 ("assistant", code),
#                 ""
#                 ])
#
#     messages.append(("system", "# User Query:"))
#     messages.append(("user", f"Q: {query}"))
#
#     messages.extend([
#         ("system", "### FINAL INSTRUCTIONS"),
#         ("system", "\n".join(OUTPUT_CONSTRAINTS))]
#     )
#
#     return messages
#
#
#
#

import re

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

def extract_or_fix_python_code(raw_text):
    PYTHON_FIX_PROMPT = f"""
    You are a Python code extractor and fixer.
    You are given a raw user message that may include explanations, markdown fences, or partial code.

    Your task:
    1. Check if the message contains Python code.
    2. If it does, extract the code.
    3. If there are any syntax errors, fix them.
    4. Return only the corrected Python code — no explanations, no comments, no markdown.

    The output must be valid Python code, and must not include any other text.
    This output will be parsed by another program.

    User message:
    {raw_text}
    """
    return llm(PYTHON_FIX_PROMPT)

def extract_or_fix_json_code(raw_text):
    JSON_FIX_PROMPT = f"""
    You are a JSON extractor and fixer.
    You are given a raw message that may include explanations, markdown fences, or partial JSON.

    Your task:
    1. Check if the message contains a JSON object or array.
    2. If it does, extract and fix the JSON if needed.
    3. Ensure all keys and string values are properly quoted.
    4. Return only valid, parseable JSON — no markdown, no explanations.

    The output must be valid JSON, and must not include any other text.
    This output will be parsed by another program.

    User message:
    {raw_text}
    """
    return llm(JSON_FIX_PROMPT)
