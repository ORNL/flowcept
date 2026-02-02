# flake8: noqa: E501
# flake8: noqa: D103

def generate_common_task_fields(current_fields):
    # TODO: make this better
    common_task_fields = """
       | Column                        | Data Type | Description |
       |-------------------------------|-------------|
    """
    common_task_fields += "| `workflow_id`                 | string | Workflow the task belongs to. Use this field when the query is asking about workflow execution |\n" if "workflow_id" in current_fields else ""
    common_task_fields += "| `task_id`                     | string | Task identifier. |\n" if "task_id" in current_fields else ""
    common_task_fields += "| `parent_task_id`              | string | A task may be directly linked to others. Use this field when the query asks for a task informed by (or associated with or linked to) other task.  |\n" if "parent_task_id" in current_fields else ""
    common_task_fields += "| `activity_id`                 | string | Type of task (e.g., 'choose_option'). Use this for \"task type\" queries. One activity_id is linked to multiple task_ids. |\n" if "activity_id" in current_fields else ""
    common_task_fields += "| `campaign_id`                 | string | A group of workflows. |\n" if "campaign_id" in current_fields else ""
    common_task_fields += "| `hostname`                    | string | Compute node name. |\n" if "hostname" in current_fields else ""
    common_task_fields += "| `agent_id`                    | string | Set if executed by an agent. |\n" if "agent_id" in current_fields else ""
    common_task_fields += "| `started_at`                  | datetime64[ns, UTC] | Start time of a task. Always use this field when the query has any temporal reference related to the workflow execution, such as 'get the first 10 workflow executions' or 'the last workflow execution'. |\n" if "started_at" in current_fields else ""
    common_task_fields += "| `ended_at`                    | datetime64[ns, UTC] | End time of a task. |\n" if "ended_at" in current_fields else ""
    common_task_fields += "| `subtype`                     | string | Subtype of a task. |\n" if "subtype" in current_fields else ""
    common_task_fields += "| `tags`                        | List[str] | List of descriptive tags. |\n" if "tags" in current_fields else ""
    common_task_fields += "| `image`                       | blob | Raw binary data related to an image. |\n" if "image" in current_fields else ""
    common_task_fields += "| `telemetry_summary.duration_sec` | float | Task duration (seconds). |\n" if "telemetry_summary.duration_sec" in current_fields else ""
    common_task_fields += "| `telemetry_summary.cpu.percent_all_diff` | float | Difference in overall CPU utilization percentage across all cores between task end and start. |\n" if "telemetry_summary.cpu.percent_all_diff" in current_fields else ""
    common_task_fields += "| `telemetry_summary.cpu.user_time_diff`   | float | Difference average per core CPU user time (seconds) between task start and end times. |\n" if "telemetry_summary.cpu.user_time_diff" in current_fields else ""
    common_task_fields += "| `telemetry_summary.cpu.system_time_diff` | float | Difference in CPU system (kernel) time (seconds) used during the task execution. |\n" if "telemetry_summary.cpu.system_time_diff" in current_fields else ""
    common_task_fields += "| `telemetry_summary.cpu.idle_time_diff`   | float | Difference in CPU idle time (seconds) during task end and start. |\n" if "telemetry_summary.cpu.idle_time_diff" in current_fields else ""

    common_task_fields += "\n For any queries involving CPU, use fields that begin with telemetry_summary.cpu"

    return common_task_fields


DF_FORM = "The user has a pandas DataFrame called `df`, created from flattened task objects using `pd.json_normalize`."

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
"""


def get_example_values_prompt(example_values):
    values_prompt = f"""    
           Now, this other dictionary below provides type (t), up to 3 example values (v), and, for lists, shape (s) and element type (et) for each field.
           Field names do not include `used.` or `generated.` They represent the unprefixed form shared across roles. String values may be truncated if they exceed the length limit.
           ```python
           {example_values}
           ```
       """
    return values_prompt


def get_df_schema_prompt(dynamic_schema, example_values, current_fields):
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

        {generate_common_task_fields(current_fields)}
        ---
    """

    values_prompt = get_example_values_prompt(example_values)
    # values_prompt = ""
    prompt = schema_prompt + values_prompt
    return prompt


def generate_plot_code_prompt(query, dynamic_schema, example_values, current_fields) -> str:
    PLOT_PROMPT = f"""
        You are a Streamlit chart expert.
        {DF_FORM}

        {get_df_schema_prompt(dynamic_schema, example_values, current_fields)}
        
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

        Your response must be only the raw Python code in the format:
        result = ...
        Except for the `result` variable, YOU MUST NEVER CREATE ANY OTHER VARIABLE. NEVER!  

        User request:
        {query}

        

    """
    return PLOT_PROMPT


JOB = "You will generate a pandas dataframe code to solve the query."
ROLE = """You are an expert in HPC workflow provenance data analysis with a deep knowledge of data lineage tracing, workflow management, and computing systems. 
            You are analyzing provenance data from a complex workflow consisting of numerous tasks."""
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
    - **When filtering by `activity_id`, only select columns that belong to that activity’s schema.**
      - Always observing the ALLOWED_FIELDS list, use only `used.` and `generated.` fields listed in the schema for that `activity_id`.
     - Explicitly list the selected columns — **never return all columns**
    - **Only include telemetry columns if used in the query logic.**
      -THERE IS NOT A FIELD NAMED `telemetry_summary.start_time` or `telemetry_summary.end_time` or `used.start_time` or `used.end_time`. Use `started_at` and `ended_at` instead when you want to find the duration of a task, activity, or workflow execution.
      -THE GENERATED FIELDS ARE LABELED AS SUCH: `generated.()` NOT `generated_output`. Any reference to `generated_output` is incorrect and should be replaced with `generated.` prefix.
      -THERE IS NOT A FIELD NAMED `execution_id` or `used.execution_id`. Look at the QUERY to decide what correct _id field to use. Any mentions of workflow use `workflow_id`. Any mentions of task use `task_id`. Any mentions of activity use `activity_id`.
      -DO NOT USE `nlargest` or `nsmallest` in the query code, use `sort_values` instead.
      -An activity with a value in the `generated.` column created that value. Whereas an activity that has a value in the `used.` column used that value from another activity. IF THE `used.` and `generated.` fields share the same letter after the dot, that means that the activity associated with the `generated.` was created by another activity and the one with `used.` used that SAME value that was created by the activity with that same value in the `generated.` field.
      -WHEN user requests about workflow time (e.g., total time or  duration" or elapsed time or total execution time or elapsed time or makespan about workflow executions or asking about workflows that took longer than a certain threshold or other workflow-related timing question of one or many workflow executions (each is identified by `workflow_id`), get its latest task's `ended_at` and its earliest task's `started_at`and compute the difference between them, like this (adapt when needed): `df.groupby('workflow_id').apply(lambda x: (x['ended_at'].max() - x['started_at'].min()).total_seconds())`
      -WHEN user requests duration or execution time per task or for individual tasks, utilize `telemetry_summary.duration_sec`. 
      -WHEN user requests execution time per activity within workflows compute durations using the difference between the last `ended_at` and the first `started_at` grouping by activitiy_id, workflow_id rather than using `telemetry_summary.duration_sec`.
      
      -The first (or the earliest) workflow execution is the one that has the task with earliest `started_at`, so you need to sort the DataFrame based on `started_at` to get the associated workflow_id.
      -The last (or the latest or the most recent) workflow execution is the one that has the task with the latest `ended_at`, so you need to sort the DataFrame based on `ended_at` to get the associated workflow_id.
      - Use this to select the tasks in the first workflow (or in the earliest workflow): df[df.workflow_id == df.loc[df.started_at.idxmin(), 'workflow_id']]
      - Use this to select the tasks in the last workflow (or in the latest workflow or in the most recent workflow or the workflow that started or ended most recently): df[df.workflow_id == df.loc[df.ended_at.idxmax(), 'workflow_id']]
      -WHEN the user requests the "first workflow" (or earliest workflow), you must identify the workflow by using workflow_id of the task with the earliest started_at. DO NOT use the min workflow_id.
      -WHEN the user requests the "last workflow" (or latest workflow or most recent workflow), you must identify the workflow by using workflow_id of the task with the latest `ended_at`. DO NOT use the max workflow_id.
      -Do not use  df['workflow_id'].max() or  df['workflow_id'].min() to find the first or last workflow execution.
      
      -To select the first (or earliest) N workflow executions, use or adapt the following: `df.groupby('workflow_id', as_index=False).agg({{"started_at": 'min'}}).sort_values(by='started_at', ascending=True).head(N)['workflow_id']` - utilize `started_at` to sort!     
      -To select the last (or latest or most recent) N workflow executions, use or adapt the following: `df.groupby('workflow_id', as_index=False).agg({{"ended_at": 'max'}}).sort_values(by='ended_at', ascending=False).head(N)['workflow_id']` - utilize `ended_at` to sort!
      
      -If the user does not ask for a specific workflow run, do not use `workflow_id` in your query. 
      -To select the first or earliest or initial tasks, use or adapt the following: `df.sort_values(by='started_at', ascending=True)`
      -To select the last or final or most recent tasks, use or adapt the following: `df.sort_values(by='ended_at', ascending=False)`
      
      -If user explicitly asks to display or show all columns or fields, do not project on any particular field or column. Just show all of them.
      
      -WHEN the user requests a "summary" of activities, you must incorporate relevant summary statistics such as min, max, and mean, into the code you generate.
      -Do NOT use df[0] or df[integer value] or df[df[<field name>].idxmax()] or df[df[<field name>].idxmin()] because these are obviously not valid Pandas Code!
      -**Do NOT use any of those: df[df['started_at'].idxmax()], df[df['started_at'].idxmin()], df[df['ended_at'].idxmin()], df[df['ended_at'].idxmax()]. Those are not valid Pandas Code.**
      - When the query mentions "each task", or "each activity", or "each workflow", make sure you show (project) the correct id column in the results (i.e., respectively: `task_id`, `activity_id`, `workflow_id`) to identify those in the results. 
      - Use df[<role>.field_name] == True or df[<role>.field_name] == False when user queries boolean fields, where <role> is either used or generated, depending on the field name. Make sure field_name is a valid field in the DataFrame.  
    
    If the query asks you to report which values appear in one or more columns
        (for example “which X were used”, “list all Y”, “what X and Y were generated”), then:

            For each relevant column, select that column from df.            
            Call .dropna() on that column to remove missing values.            
            After dropping NaNs, apply .unique(), .value_counts(), or any other aggregation as needed.            
            Select that column.            
            Call .dropna() on it.            
            Then call .unique(), .value_counts(), or any other aggregation.
            

    - **Do not include metadata columns unless explicitly required by the user query.**
"""

FEW_SHOTS = """
  ### 5. Few-Shot Examples

    # Q: How many tasks were processed?
    result = len(df)) 

    # Q: How many tasks for each activity?
    result = df['activity_id'].value_counts()

"""
# # Q: What is the average loss across all tasks?
# result = df['generated.loss'].mean()
#
# # Q: select the 'choose_option' tasks executed by the agent, and show the planned controls, generated option, scores, explanations
# result = df[(df['activity_id'] == 'choose_option') & (df['agent_id'].notna())][
#     ['used.planned_controls', 'generated.option', 'used.scores.scores', 'generated.explanation']].copy()
#
# # Q: Show duration and generated scores for 'simulate_layer' tasks
# result = df[df['activity_id'] == 'simulate_layer'][['telemetry_summary.duration_sec', 'generated.scores']]

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


def generate_pandas_code_prompt(query: str, dynamic_schema, example_values, custom_user_guidances, current_fields):
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
    prompt = (
        f"{ROLE}"
        f"{JOB}"
        f"{DF_FORM}"
        f"{curr_cols}"
        f"{get_df_schema_prompt(dynamic_schema, example_values, current_fields)}"  # main tester
        f"{QUERY_GUIDELINES}"  # main tester
        f"{FEW_SHOTS}"  # main tester
        f"{custom_user_guidance_prompt}"
        f"{OUTPUT_FORMATTING}"
        "User Query:"
        f"{query}"
    )
    return prompt


def dataframe_summarizer_context(code, reduced_df, dynamic_schema, example_values, query, current_fields) -> str:
    job = "You are a Workflow Provenance Specialist analyzing a DataFrame that was obtained to answer a query."

    if "image" in reduced_df.columns:
        reduced_df = reduced_df.drop(columns=["image"])

    prompt = f"""
    {job}
    
     Given:
    
    **User Query**:  
    {query}
    
    **Query_Code**:  
    {code}
    
    **Reduced DataFrame `df` contents** (rows sampled from full result):  
    {reduced_df}
    
    **Original df (before reduction) had this schema:
    {get_df_schema_prompt(dynamic_schema, example_values, current_fields)}
    
    Your task is to find a concise and direct answer as an English sentence to the user query.
        
    Only if the answer to the query is complex, provide more explanation by: 
        1. Analyzing the DataFrame values and columns for any meaningful or notable information. 
        2. Comparing the query_code with the data content to understand what the result represents. THIS IS A REDUCED DATAFRAME, the original dataframe, used to answer the query, may be much bigger. IT IS ALREADY KNOWN! Do not need to restate this.
        3. If it makes sense, provide information beyond the recorded provenance, but state it clearly that you are inferring it.
    
    In the end, conclude by giving your concise answer as follows: **Response**: <YOUR ANSWER>

    Note that the user should not know that this is a reduced dataframe. 
    Keep your response short and focused.

    """

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


def extract_or_fix_python_code_prompt(raw_text, current_fields):
    prompt = f"""
    You are a Pandas DataFrame code extractor and fixer. Pandas is a well-known data science Python library for querying datasets. 
    You are given a raw user message that may include explanations, markdown fences, or partial DataFrame code that queries a DataFrame `df`.

    Your task:
    1. Check if the message contains a valid DataFrame code.
    2. If it does, extract the code.
    3. If there are any syntax errors, fix them.
    4. Carefully analyze the list of columns in the query. The query must only use fields in this list:
        ALLOWED_FIELDS = {current_fields}.
       If there are fields not in this list, replace the fields to match according to the ALLOWED_FIELDS list.  
    5. Return only the corrected DataFrame query code — no explanations, no comments, no markdown.

    The output must be valid Python code, and must not include any other text.
    Your output can only contain fields in the ALLOWED_FIELDS list.
    This output will be parsed by another program.
    
    ONCE AGAIN, ONLY PRODUCE THE PYTHON CODE. DO NOT SAY ANYTHING ELSE!
    
    User message:
    {raw_text}
    """
    return prompt
