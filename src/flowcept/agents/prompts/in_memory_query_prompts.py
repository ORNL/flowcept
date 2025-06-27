
COMMON_TASK_FIELDS = """
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
    """

def get_df_schema_prompt(dynamic_schema):
    prompt = f"""
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

        {COMMON_TASK_FIELDS}
        ---
    """
    return prompt

def generate_plot_code_prompt(query, dynamic_schema) -> str:
    PLOT_PROMPT = f"""
        You are a Streamlit chart expert. The user has a pandas DataFrame called `df`, created from flattened task objects using `pd.json_normalize`.

        {get_df_schema_prompt(dynamic_schema)}
        
        ### 3. Guidelines

        - When plotting from a grouped or aggregated result, set an appropriate column (like activity_id, started_at, etc.) as the index before plotting to ensure x-axis labels are correct.
        - When aggregating by "activity_id", remember to include .set_index('activity_id') in your response. 

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

        THE OUTPUT MUST BE A VALID JSON ONLY. DO NOT SAY ANYTHING ELSE.

    """
    return PLOT_PROMPT

def generate_pandas_code_prompt(query: str, dynamic_schema):
    prompt = f"""
    You are a Workflow Provenance Data Science Expert working with a flattened pandas DataFrame named `df`, created using `pd.json_normalize(tasks)`.

    {get_df_schema_prompt(dynamic_schema)}
    
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

    THE OUTPUT MUST BE A VALID PYTHON CODE ONLY. DO NOT SAY ANYTHING ELSE.

    Strictly follow the constraints above.

    User Query:
    {query}
    """
    return prompt


def dataframe_summarizer_context(code, cols_str, summary_reason, summary_text, query) -> str:
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
    return prompt

def extract_or_fix_json_code_prompt(raw_text) -> str:
    prompt = f"""
    You are a JSON extractor and fixer.
    You are given a raw message that may include explanations, markdown fences, or partial JSON.

    Your task:
    1. Check if the message contains a JSON object or array.
    2. If it does, extract and fix the JSON if needed.
    3. Ensure all keys and string values are properly quoted.
    4. Return only valid, parseable JSON — no markdown, no explanations.

    THE OUTPUT MUST BE A VALID JSON ONLY. DO NOT SAY ANYTHING ELSE.

    User message:
    {raw_text}
    """
    return prompt

def extract_or_fix_python_code_prompt(raw_text):
    prompt = f"""
    You are a Pandas DataFrame code extractor and fixer. Pandas is a well-known data science Python library for querying datasets. 
    You are given a raw user message that may include explanations, markdown fences, or partial DataFrame code that queries a DataFrame `df`.

    Your task:
    1. Check if the message contains a valid DataFrame code.
    2. If it does, extract the code.
    3. If there are any syntax errors, fix them.
    4. Return only the corrected DataFrame query code — no explanations, no comments, no markdown.

    The output must be valid Python code, and must not include any other text.
    This output will be parsed by another program.

    User message:
    {raw_text}
    """
    return prompt