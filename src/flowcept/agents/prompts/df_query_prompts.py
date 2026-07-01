# flake8: noqa: E501
"""Prompt builders for DF (DataFrame) chat query path.

All functions are plain Python — no MCP framework decorators.
The ``@mcp_flowcept.prompt()`` registration lives in ``prompts/mcp_prompts.py``.
"""

from flowcept.agents.prompts.schema_prompt_context import (
    build_allowed_fields_prompt,
    build_example_values_prompt,
    build_task_structure_prompt,
)


def build_df_chat_rules(
    query_tool: str,
    objects_tool: str,
    list_agents_tool: str,
    workflow_context_tool: str,
) -> str:
    """Return the DF-mode chat rules block.

    Parameters
    ----------
    query_tool : str
        Name of the tool used to execute pandas queries against the task DataFrame.
    objects_tool : str
        Name of the tool used to query artifact/object DataFrames.
    list_agents_tool : str
        Name of the tool used to list agent summaries with human-readable names.
    workflow_context_tool : str
        Name of the tool used to retrieve workflow-level metadata.
    """
    return (
        "DATAFRAME MODE — You are operating in in-memory DataFrame mode.\n"
        f"RULE 1: Call `{query_tool}(code=<pandas_code>)` to query task data.\n"
        f"RULE 1b: If `{query_tool}` returns only column names, make a second call"
        " that queries the actual data values using those column names.\n"
        "RULE 1c: The DataFrame `df` contains all tasks loaded for the current session."
        " It is pre-filtered by session setup — NEVER add scope-limiting identifier"
        " filters (workflow or campaign identifiers) to your pandas code; doing so may"
        " return 0 results. For total task counts, use `len(df)` on the full df.\n"
        "RULE 2: The pandas code MUST assign output to `result`."
        " Use ONLY the columns listed in the DataFrame schema below.\n"
        f"RULE 3: For questions that ask for a complete list of all activities in the workflow"
        f" (full lineage, execution flow, or activity enumeration), call `{query_tool}` to retrieve"
        f" the distinct activity identifiers from the task data."
        f" Do NOT attempt to compute upstream/downstream data-flow relationships in pandas"
        f" — just enumerate all distinct activities."
        f" When the question is compound (asking for enumeration alongside a specific filter"
        f" such as 'best', 'highest', or 'around task X'), answer the enumeration part first"
        f" from the same query result — do NOT run targeted lookup queries before enumerating.\n"
        "RULE 4: NEVER write pandas code (`result = ...`) in your text response.\n"
        f"RULE 5: For artifact property questions — meaning questions about the specifications,"
        f" properties, design characteristics, or stored metadata of workflow artifacts"
        f" (stored binary objects, data files, or versioned outputs) — call `{objects_tool}` instead of"
        f" `{query_tool}`. Report all returned field values verbatim.\n"
        "RULE 6: Task timestamp fields may be stored as ISO-format strings;"
        " use `pd.to_datetime()` when sorting or computing differences"
        " (execution order, wall-clock duration).\n"
        f"RULE 7: For questions about which agent or task submitted or dispatched work items:"
        f" (1) Call `{list_agents_tool}` to get known agent identifiers."
        f" (2) Call `{query_tool}` to retrieve rows from the full DataFrame where the agent"
        f" attribution column is not null — do NOT filter to only the target activity rows."
        f" The submitting task is the one whose activity name implies dispatching or submitting;"
        f" its agent attribution column identifies the responsible agent."
        f" Always report the agent name and the submitting activity name verbatim.\n"
        f"RULE 8: For workflow-level questions (name, campaign, user, timestamps,"
        f" or listing workflows), call `{workflow_context_tool}` —"
        " task rows do not contain workflow-level metadata.\n"
        f"RULE 8b: For questions that explicitly ask about hardware, machine, processor,"
        f" or platform (NOT questions about activities, lineage, or workflow structure),"
        f" call `{query_tool}` to query task rows for machine placement and resource data.\n"
        f"RULE 9: When executing the MANDATORY COMPARISON PROTOCOL (Step 1 search for reference"
        f" entity Y), your FIRST tool call MUST be `{objects_tool}` — the entity may be a workflow"
        f" artifact. Only if Y is absent from objects should you then call `{query_tool}` to check tasks.\n"
    )


def get_df_form(context_kind="tasks"):
    """Return DataFrame context description string."""
    if context_kind == "objects":
        return "The user has a pandas DataFrame called `df`, created from flattened object metadata messages using `pd.json_normalize`."
    return "The user has a pandas DataFrame called `df`, created from flattened task objects using `pd.json_normalize`."


def build_current_df_columns_prompt(current_fields) -> str:
    """Build the authoritative DataFrame field constraint."""
    return (
        build_allowed_fields_prompt(current_fields, target_name="df")
        + '- If the query cannot be answered using ALLOWED_FIELDS, return exactly: result = "info not available"\n'
    )


def get_example_values_prompt(example_values):
    """Return example values prompt string."""
    return build_example_values_prompt(example_values)


def get_object_schema_prompt(example_values, current_fields):
    """Return schema prompt for object context."""
    schema_prompt = """
     ## DATAFRAME STRUCTURE

        Each row in `df` represents one workflow object metadata message.

        Important object fields:
        - `object_type`: semantic object category (user-defined label, e.g. input_file, dataset, artifact).
        - `type`: Flowcept message type. For object rows this is usually "object"; do not use it as the object category.
        - `file_path`: object path when available.
        - `workflow_id`: workflow associated with the object.
        - `custom_metadata.*`: user-defined metadata fields; check ALLOWED_FIELDS for available sub-fields.

        ALWAYS CHECK THE ALLOWED_FIELDS list before proceeding.
        ---
    """
    return schema_prompt + get_example_values_prompt(example_values)


def get_df_schema_prompt(dynamic_schema, example_values, current_fields, context_kind="tasks"):
    """Return the full DataFrame schema prompt."""
    if context_kind == "objects":
        return get_object_schema_prompt(example_values, current_fields)

    return build_task_structure_prompt(
        dynamic_schema=dynamic_schema,
        example_values=example_values,
        current_fields=current_fields,
        record_description="Each row in `df` represents a single task.",
    )


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
        - Prefer bar charts (`st.bar_chart`) when the x-axis has ≤10 discrete categories (e.g., category labels, discrete parameter values). Use line charts only for continuous/time-series data.

        ### 4. Output Format

        You must write Python code using Streamlit (st) to visualize the requested data.

        - Always assume `df` is already defined.
        - First, assign the query result to a variable called `result` using pandas.
        - Then, write the plotting code based on `result`.
        - Return a Python dictionary with three fields:
          - `"result_code"`: the pandas code that assigns `result`
          - `"plot_code"`: the code that creates the Streamlit plot
          - `"description"`: a one-sentence natural-language caption. It MUST include:
            (1) the chart type (e.g., "bar chart", "line chart"),
            (2) the exact field names from result_code verbatim (e.g., "generated.output_field", "used.input_param"),
            (3) the grouping/index column name,
            (4) if discrete categories are involved, list them explicitly.
        ---

        ### 5. Few-Shot Examples

        ```python
        # Q: Plot the number of tasks by activity
        {{
          "result_code": "result = df['activity_id'].value_counts().reset_index().rename(columns={{'index': 'activity_id', 'activity_id': 'count'}})",
          "plot_code": "st.bar_chart(result.set_index('activity_id'))",
          "description": "A bar chart of task count by activity_id."
        }}

        # Q: Show a line chart of task duration per task start time
        {{
          "result_code": "result = df[['started_at', 'telemetry_summary.duration_sec']].dropna().set_index('started_at')",
          "plot_code": "st.line_chart(result)",
          "description": "A line chart of telemetry_summary.duration_sec over started_at."
        }}

        Your response must be ONLY a raw JSON object (no markdown fences, no prose), in this exact format:
        {{"result_code": "<pandas code that assigns result>", "plot_code": "<Streamlit plotting code>", "description": "<one-sentence caption>"}}

        User request:
        {query}
    """


JOB = "You will generate a pandas dataframe code to solve the query."
ROLE = """You are an expert in workflow provenance data analysis with a deep knowledge of data lineage tracing, workflow management, and computing systems.
            You are analyzing provenance data from a complex workflow consisting of numerous tasks."""
OBJECT_ROLE = """You are an expert in workflow provenance data analysis with a deep knowledge of data lineage tracing, workflow management, and computing systems.
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

    - **For filter+aggregate queries** (e.g., "average X for items where Y > Z"): return a DataFrame showing every row that passed the filter (with its key identification columns like item_id or entity_id and the filtered field), not just a scalar aggregate. Include the aggregate as a new column or let the summary describe it.
    - **For compound queries asking multiple questions in one sentence**: return a single DataFrame that captures all parts. NEVER return a Python list, tuple, or mixed-type collection. Instead build a structured DataFrame.
    - **To count output fields per activity**: use `gen_cols = [c for c in df.columns if c.startswith('generated.')]` to get generated columns, then use `df.groupby('activity_id')[gen_cols].apply(lambda g: int(g.notna().sum().sum()))` to count the total number of non-null generated field values per activity (this accounts for how many tasks of each activity ran, so a task type that ran 5 times will rank higher than one that ran once even if each has the same number of fields).
    - **For filter+aggregate queries**: ALWAYS include the primary identifier column(s) for the activity (e.g., any config, item, or entity ID from the schema) in the result DataFrame, so the reader can identify each row without relying on task_id.
"""

OBJECT_QUERY_GUIDELINES = """
    ### 3. Query Guidelines

    - Use `df` as the base DataFrame.
    - Use `object_type` for object category questions.
    - Use `file_path` for file path questions.
    - Use `custom_metadata.*` fields for object-specific metadata (check ALLOWED_FIELDS for available sub-fields).
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

    # Q: List all distinct object types
    result = df['object_type'].dropna().unique()

"""

OUTPUT_FORMATTING = """
    6. Final Instructions
    Return only valid pandas code assigned to the variable result.

    Your response must be only the raw Python code in the format:
        result = ...

    For simple queries: one line is preferred.
    For compound queries that require intermediate variables: use multiple lines (e.g., define gen_cols, per_act, etc., then assign result on the last line).

    Do not include: Explanations, Markdown formatting, Triple backticks, Comments, or Any text before or after the code block.
    The output cannot have any markdown, no ```python or ``` at all.

    THE LAST LINE OF YOUR CODE MUST BE: result = ...

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

    curr_cols = build_current_df_columns_prompt(current_fields)
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

    Your task is to produce a concise English answer to the user query.

    Mandatory requirements:
    1. Mirror the user's exact vocabulary. If the query says "best", write "best" (not "highest" or "top").
       If the query says "worst", write "worst" (not "lowest").
    2. For queries that find an extremal result (best, worst, highest, lowest, max, min, first, last):
       - Name the full set that was searched (e.g., "across all tasks of that activity_id" or "among all records returned").
       - Describe the method: "found by sorting on [column name verbatim] in [ascending/descending] order".
    3. For queries that filter by a condition:
       - Explicitly enumerate every item that passed the filter with its relevant field values
         (e.g., "item_a (field=value_a), item_b (field=value_b), and item_c (field=value_c)").
       - Then state the aggregate result.
    4. Always include column names verbatim using dot-notation (e.g., "generated.metric_a", "used.param_a").
       When code uses wildcards like "generated.*", look up the actual field names from the schema
       and enumerate key specific fields. Use the word "including" when listing output field names.

    In the end, conclude by giving your concise answer as follows: **Response**: <YOUR ANSWER>

    Note that the user should not know that this is a reduced dataframe.
    Keep your response focused and complete.
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


def build_extract_or_fix_python_code_prompt(raw_text, current_fields, runtime_error: str = None) -> str:
    """Build a prompt to extract or fix pandas code from raw text.

    Parameters
    ----------
    raw_text : str
        Raw text possibly containing Python code.
    current_fields : list
        Available DataFrame column names.
    runtime_error : str, optional
        Exception message from a previous execution attempt.  When provided,
        the prompt explicitly asks the LLM to fix the runtime error.

    Returns
    -------
    str
        Formatted prompt.
    """
    error_section = (
        f"\n    The code previously raised this runtime error — you MUST fix it:\n    {runtime_error}\n"
        if runtime_error
        else ""
    )
    return f"""
    You are a Pandas DataFrame code extractor and fixer.
    You are given a raw user message that may include explanations, markdown fences, or partial DataFrame code that queries a DataFrame `df`.
{error_section}
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
