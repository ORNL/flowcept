# flake8: noqa: E501
"""Prompt builders for in-memory task DataFrame queries.

All functions are plain Python — no MCP framework decorators.
The ``@mcp_flowcept.prompt()`` registration lives in ``prompts/mcp_prompts.py``.
"""

from flowcept.agents.provenance_schema_manager.static_schema_builder import SCHEMA_CONTEXT


def _build_task_field_table(current_fields) -> str:
    """Build a markdown table of task fields using SCHEMA_CONTEXT, filtered to current_fields."""
    rows = [
        "   | Column                        | Data Type | Description |",
        "   |-------------------------------|-----------|-------------|",
    ]
    for field in SCHEMA_CONTEXT.get("task_fields", []):
        if field["name"] in current_fields:
            rows.append(f"   | `{field['name']:<30}` | {field['type']:<9} | {field['description']} |")
    for field in SCHEMA_CONTEXT.get("telemetry_summary_fields", []):
        full_name = f"telemetry_summary.{field['name']}"
        if full_name in current_fields:
            rows.append(f"   | `{full_name:<30}` | {field['type']:<9} | {field['description']} |")
    if any(f.startswith("telemetry_summary.cpu") for f in current_fields):
        rows.append("   \n For any queries involving CPU, use fields that begin with telemetry_summary.cpu")
    return "\n".join(rows)


def get_df_form(context_kind="tasks"):
    """Return DataFrame context description string."""
    if context_kind == "objects":
        return "The user has a pandas DataFrame called `df`, created from flattened object metadata messages using `pd.json_normalize`."
    return "The user has a pandas DataFrame called `df`, created from flattened task objects using `pd.json_normalize`."


CURRENT_DF_COLUMNS_PROMPT = """
### ABSOLUTE FIELD CONSTRAINT -- THIS IS CRITICAL

The following list is the ONLY valid field names in df. Treat this as the schema:

ALLOWED_FIELDS = [COLS]

You MUST treat this list as authoritative.

- You may only use fields names that appear EXACTLY (string match) in ALLOWED_FIELDS.
- You are NOT allowed to create new field names by:
  - adding or removing prefixes like "used." or "generated."
  - combining words
  - guessing.
- If a field name is not in ALLOWED_FIELDS, you MUST NOT use it.
- If the query cannot be answered using ALLOWED_FIELDS, return exactly: result = "info not available"
"""


def get_example_values_prompt(example_values):
    """Return example values prompt string."""
    return f"""
           Now, this other dictionary below provides type (t), up to 3 example values (v), and, for lists, shape (s) and element type (et) for each field.
           Field names do not include `used.` or `generated.` They represent the unprefixed form shared across roles. String values may be truncated if they exceed the length limit.
           ```python
           {example_values}
           ```
       """


def get_object_schema_prompt(example_values, current_fields):
    """Return schema prompt for object context."""
    schema_prompt = """
     ## DATAFRAME STRUCTURE

        Each row in `df` represents one workflow object metadata message.

        Important object fields:
        - `object_type`: semantic object category, such as input_file, dataset, artifact, or ml_model.
        - `type`: Flowcept message type. For object rows this is usually "object"; do not use it as the object category.
        - `object_size_bytes`: object payload size in bytes.
        - `file_path`: object path when available.
        - `workflow_id`: workflow associated with the object.

        ALWAYS CHECK THE ALLOWED_FIELDS list before proceeding.
        ---
    """
    return schema_prompt + get_example_values_prompt(example_values)


def get_df_schema_prompt(dynamic_schema, example_values, current_fields, context_kind="tasks"):
    """Return the full DataFrame schema prompt."""
    if context_kind == "objects":
        return get_object_schema_prompt(example_values, current_fields)

    schema_prompt = f"""
     ## DATAFRAME STRUCTURE

        Each row in `df` represents a single task.

        ### 1. Structured task fields:

        - **in**: input parameters (columns starting with `used.`)
        - **out**: output metrics/results (columns starting with `generated.`)

        The schema for these fields is defined in the dictionary below.
        It maps each activity ID to its inputs (i) and outputs (o), using flattened field names that include `used.` or `generated.` prefixes to indicate the role the field played in the task. These names match the columns in the dataframe `df`.

        {dynamic_schema}
        Use this schema and fields to understand what inputs and outputs are valid for each activity.

        IMPORTANT: The user might say used for outputs or generated for inputs, which might confuse you. Do not get tricked by the user.
         Ignore the natural-language words "used" and "generated".
            - The English phrase "used in the calculation" does NOT mean you must use a `used.` column.
            - The English word "generated" in the question does NOT force you to use a `generated.` column either.

         ALWAYS CHECK THE ALLOWED_FIELDS list before proceeding. THIS IS CRITICAL.

        ### 2. Additional fields for tasks:

        {_build_task_field_table(current_fields)}
        ---
    """

    return schema_prompt + get_example_values_prompt(example_values)


def build_plot_code_prompt(query, dynamic_schema, example_values, current_fields, context_kind="tasks") -> str:
    """Build a prompt for Streamlit chart code generation.

    Parameters
    ----------
    query : str
        Natural language query.
    dynamic_schema : dict
        DataFrame schema.
    example_values : dict
        Example values.
    current_fields : list
        Current DataFrame columns.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    str
        Formatted prompt.
    """
    return f"""
        You are a Streamlit chart expert.
        {get_df_form(context_kind)}

        {get_df_schema_prompt(dynamic_schema, example_values, current_fields, context_kind=context_kind)}

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

        Your response must be only the raw Python code in the format:
        result = ...
        Except for the `result` variable, YOU MUST NEVER CREATE ANY OTHER VARIABLE. NEVER!

        User request:
        {query}
    """


JOB = "You will generate a pandas dataframe code to solve the query."
ROLE = """You are an expert in HPC workflow provenance data analysis with a deep knowledge of data lineage tracing, workflow management, and computing systems.
            You are analyzing provenance data from a complex workflow consisting of numerous tasks."""
OBJECT_ROLE = """You are an expert in HPC workflow provenance data analysis with a deep knowledge of data lineage tracing, workflow management, and computing systems.
            You are analyzing object metadata records from a workflow provenance buffer."""
QUERY_GUIDELINES = """

    ### 3. Query Guidelines

    - Use `df` as the base DataFrame.
    - Use `activity_id` to filter by task type (valid values = schema keys).
    - ONLY IF the ALLOWED_FIELDS list allow, use `used.` for parameters (inputs) and `generated.` for outputs (metrics).
    - Use `telemetry_summary.duration_sec` for performance-related questions.
    - Use `hostname` when user mentions *where* a task ran.
    - Use `agent_id` when the user refers to agents (non-null means task was agent-run).

    ### 4. Hard Constraints (obey strictly, YOUR LIFE DEPENDS ON THEM. DO NOT HALLUCINATE!!!)

    - Always return code in the form `result = df[<filter>][[...]]` or `result = df.loc[<filter>, [...]]`
     -**THERE ARE NOT INDIVIDUAL FIELDS NAMED `used` OR `generated`, they are ONLY are prefixes to the field names.**
     - If the query needs fields that begin with `used.` or `generated.`, your generated query needs to iterate over the df.columns to select the used or generated fields only, such as (adapt when needed): `[col for col in df.columns if col.startswith('generated.')]` or `[col for col in df.columns if col.startswith('used.')]`
     **THERE ABSOLUTELY ARE NO FIELDS NAMED `used` or `generated`. DO NOT, NEVER use the string 'used' or 'generated' in your generated code!!!**
    **THE COLUMN 'used' DOES NOT EXIST**
    **THE COLUMN 'generated' DOES NOT EXIST**
    - **When filtering by `activity_id`, only select columns that belong to that activity's schema.**
      - Always observing the ALLOWED_FIELDS list, use only `used.` and `generated.` fields listed in the schema for that `activity_id`.
     - Explicitly list the selected columns — **never return all columns**
    - **Only include telemetry columns if used in the query logic.**
      -THERE IS NOT A FIELD NAMED `telemetry_summary.start_time` or `telemetry_summary.end_time`. Use `started_at` and `ended_at` instead.
      -THE GENERATED FIELDS ARE LABELED AS SUCH: `generated.()` NOT `generated_output`.
      -THERE IS NOT A FIELD NAMED `execution_id` or `used.execution_id`.
      -DO NOT USE `nlargest` or `nsmallest` in the query code, use `sort_values` instead.
      -WHEN user requests about workflow time, get its latest task's `ended_at` and its earliest task's `started_at` and compute the difference.
      -WHEN user requests duration per task, utilize `telemetry_summary.duration_sec`.

    If the query asks you to report which values appear in one or more columns, then:
        For each relevant column, select that column from df, call .dropna(), then .unique() or .value_counts().

    - **CRITICAL — list-valued columns**: NEVER call `.unique()` or `.value_counts()` directly on list-valued columns.
      Always call `.explode()` first to flatten the lists into individual rows, then aggregate.

    - **Do not include metadata columns unless explicitly required by the user query.**
"""

OBJECT_QUERY_GUIDELINES = """
    ### 3. Query Guidelines

    - Use `df` as the base DataFrame.
    - Use `object_type` for object category questions.
    - Use `object_size_bytes` for object size questions.
    - Use `file_path` for file path questions.
    - Use `workflow_id` when the query asks for workflow-specific objects.
    - The column `type` is the Flowcept message type, not the object category.
    - Explicitly list selected columns unless the user asks for all columns.
"""

FEW_SHOTS = """
  ### 5. Few-Shot Examples

    # Q: How many tasks were processed?
    result = len(df)

    # Q: How many tasks for each activity?
    result = df['activity_id'].value_counts()

"""

OBJECT_FEW_SHOTS = """
  ### 5. Few-Shot Examples

    # Q: How many objects are available?
    result = len(df)

    # Q: List all input files larger than 100 MB
    result = df[(df['object_type'] == 'input_file') & (df['object_size_bytes'] > 100 * 1000 * 1000)][['workflow_id', 'file_path', 'object_size_bytes']]

"""

OUTPUT_FORMATTING = """
    6. Final Instructions
    Return only valid pandas code assigned to the variable result.

    Your response must be only the raw Python code in the format:
        result = ...

    Do not include: Explanations, Markdown formatting, Triple backticks, Comments, or Any text before or after the code block.
    The output cannot have any markdown, no ```python or ``` at all.

    THE OUTPUT MUST BE ONE LINE OF VALID PYTHON CODE ONLY, DO NOT SAY ANYTHING ELSE.

    Strictly follow the constraints above.
"""


def build_pandas_code_prompt(
    query: str, dynamic_schema, example_values, custom_user_guidances, current_fields, context_kind="tasks"
) -> str:
    """Build a pandas code generation prompt from a natural language query.

    Parameters
    ----------
    query : str
        Natural language query.
    dynamic_schema : dict
        DataFrame schema.
    example_values : dict
        Example values.
    custom_user_guidances : list, optional
        Custom guidance strings.
    current_fields : list
        Current DataFrame columns.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    str
        Formatted prompt.
    """
    if custom_user_guidances is not None and isinstance(custom_user_guidances, list) and len(custom_user_guidances):
        concatenated_guidance = "\n".join(f"- {msg}" for msg in custom_user_guidances)
        custom_user_guidance_prompt = (
            f"You MUST consider the following guidance from the user:\n"
            f"{concatenated_guidance}"
            "------------------------------------------------------"
        )
    else:
        custom_user_guidance_prompt = ""

    curr_cols = CURRENT_DF_COLUMNS_PROMPT.replace("[COLS]", str(current_fields))
    role = OBJECT_ROLE if context_kind == "objects" else ROLE
    query_guidelines = OBJECT_QUERY_GUIDELINES if context_kind == "objects" else QUERY_GUIDELINES
    few_shots = OBJECT_FEW_SHOTS if context_kind == "objects" else FEW_SHOTS
    return (
        f"{role}"
        f"{JOB}"
        f"{get_df_form(context_kind)}"
        f"{curr_cols}"
        f"{get_df_schema_prompt(dynamic_schema, example_values, current_fields, context_kind=context_kind)}"
        f"{query_guidelines}"
        f"{few_shots}"
        f"{custom_user_guidance_prompt}"
        f"{OUTPUT_FORMATTING}"
        "User Query:"
        f"{query}"
    )


def build_dataframe_summarizer_prompt(
    code, reduced_df, dynamic_schema, example_values, query, current_fields, context_kind="tasks"
) -> str:
    """Build a prompt that asks the LLM to summarize a query result DataFrame.

    Parameters
    ----------
    code : str
        The pandas code that produced the result.
    reduced_df : pandas.DataFrame
        A reduced/sampled version of the result.
    dynamic_schema : dict
        DataFrame schema.
    example_values : dict
        Example values.
    query : str
        The original user query.
    current_fields : list
        Current DataFrame columns.
    context_kind : str, optional
        "tasks" or "objects".

    Returns
    -------
    str
        Formatted summarization prompt.
    """
    job = "You are a Workflow Provenance Specialist analyzing a DataFrame that was obtained to answer a query."

    if "image" in reduced_df.columns:
        reduced_df = reduced_df.drop(columns=["image"])

    return f"""
    {job}

     Given:

    **User Query**:
    {query}

    **Query_Code**:
    {code}

    **Reduced DataFrame `df` contents** (rows sampled from full result):
    {reduced_df}

    **Original df (before reduction) had this schema:
    {get_df_schema_prompt(dynamic_schema, example_values, current_fields, context_kind=context_kind)}

    Your task is to find a concise and direct answer as an English sentence to the user query.

    Only if the answer to the query is complex, provide more explanation by:
        1. Analyzing the DataFrame values and columns for any meaningful or notable information.
        2. Comparing the query_code with the data content to understand what the result represents.
        3. If it makes sense, provide information beyond the recorded provenance, but state it clearly that you are inferring it.

    In the end, conclude by giving your concise answer as follows: **Response**: <YOUR ANSWER>

    Note that the user should not know that this is a reduced dataframe.
    Keep your response short and focused.
    """


def extract_or_fix_json_code_prompt(raw_text) -> str:
    """Build a prompt to extract or fix JSON from raw text.

    Parameters
    ----------
    raw_text : str
        Raw text possibly containing JSON.

    Returns
    -------
    str
        Formatted prompt.
    """
    return f"""
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


def build_extract_or_fix_python_code_prompt(raw_text, current_fields) -> str:
    """Build a prompt to extract or fix pandas code from raw text.

    Parameters
    ----------
    raw_text : str
        Raw text possibly containing Python code.
    current_fields : list
        Available DataFrame column names.

    Returns
    -------
    str
        Formatted prompt.
    """
    return f"""
    You are a Pandas DataFrame code extractor and fixer.
    You are given a raw user message that may include explanations, markdown fences, or partial DataFrame code that queries a DataFrame `df`.

    Your task:
    1. Check if the message contains a valid DataFrame code.
    2. If it does, extract the code.
    3. If there are any syntax errors, fix them.
    4. Carefully analyze the list of columns in the query. The query must only use fields in this list:
        ALLOWED_FIELDS = {current_fields}.
       If there are fields not in this list, replace the fields to match according to the ALLOWED_FIELDS list.
    5. Return only the corrected DataFrame query code — no explanations, no comments, no markdown.

    ONCE AGAIN, ONLY PRODUCE THE PYTHON CODE. DO NOT SAY ANYTHING ELSE!

    User message:
    {raw_text}
    """
