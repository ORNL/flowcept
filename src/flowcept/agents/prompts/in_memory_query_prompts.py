
COMMON_TASK_FIELDS = """
    | Column                        | Data Type | Description |
    |-------------------------------|-------------|
    | `workflow_id`                 | string | Workflow the task belongs to. Use this field when the query is asking about workflow execution |
    | `task_id`                     | string | Task identifier. |
    | `parent_task_id`              | string | A task may be directly linked to others. Use this field when the query asks for a task informed by (or associated with or linked to) other task.  |
    | `activity_id`                 | string | Type of task (e.g., 'choose_option'). Use this for "task type" queries. One activity_id is linked to multiple task_ids. |
    | `campaign_id`                 | string | A group of workflows. |
    | `hostname`                    | string | Compute node name. |
    | `agent_id`                    | string | Set if executed by an agent. |
    | `started_at`                  | datetime64[ns, UTC] | Start time of a task. Always use this field when the query is has any temporal reference related to the workflow execution, such as 'get the first 10 workflow executions' or 'the last workflow execution'. |
    | `ended_at`                    | datetime64[ns, UTC] | End time of a task. | 
    | `subtype`                     | string | Subtype of a task. |
    | `tags`                        | List[str] | List of descriptive tags. |
    | `telemetry_summary.duration_sec` | float | Task duration (seconds). Use this for |
    | `telemetry_summary.cpu.percent_all_diff` | float | Difference in overall CPU utilization percentage across all cores between task end and start.|
    | `telemetry_summary.cpu.user_time_diff`   | float |  Difference average per core CPU user time ( seconds ) between task start and end times.|
    | `telemetry_summary.cpu.system_time_diff` | float |  Difference in CPU system (kernel) time (seconds) used during the task execution.|
    | `telemetry_summary.cpu.idle_time_diff`   | float |  Difference in CPU idle time (seconds) during task end and start.|
    ---
    For any queries involving CPU, use fields that begin with telemetry_summary.cpu
    """

DF_FORM = "The user has a pandas DataFrame called `df`, created from flattened task objects using `pd.json_normalize`."


def get_df_schema_prompt(dynamic_schema, example_values):
    prompt = f"""
     ## DATAFRAME STRUCTURE

        Each row in `df` represents a single task.

        ### 1. Structured task fields:

        - **in**: input parameters (columns starting with `used.`)
        - **out**: output metrics/results (columns starting with `generated.`)
       
        The schema for these fields is defined in the dictionary below.
        It maps each activity ID to its inputs (i) and outputs (o), using flattened field names that include `used.` or `generated.` prefixes to indicate the role the field played in the task. These names match the columns in the dataframe `df`.
        
        ```python
        {dynamic_schema}
        ```
        
        Now, this other dictionary below provides type (t), up to 3 example values (v), and, for lists, shape (s) and element type (et) for each field.
        Field names do not include `used.` or `generated.` They represent the unprefixed form shared across roles. String values may be truncated if they exceed the length limit.
        ```python
        {example_values}
        ```
        Use this schema and fields to understand what inputs and outputs are valid for each activity.
        
        Use df[<role>.field_name] == True or df[<role>.field_name] == False when user queries boolean fields, where <role> is either used or generated, depending on the field name. Make sure field_name is a valid field in the DataFrame.  

        ### 2. Additional fields for tasks 

        {COMMON_TASK_FIELDS}
        ---
    """
    return prompt

def generate_plot_code_prompt(query, dynamic_schema, example_values) -> str:
    PLOT_PROMPT = f"""
        You are a Streamlit chart expert.
        {DF_FORM}

        {get_df_schema_prompt(dynamic_schema, example_values)}
        
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
JOB= "You will generate a pandas dataframe code to solve the query."
ROLE= """You are an expert in HPC workflow provenance analysis with a deep knowledge of data lineage tracing, workflow management, and computing systems. 
            You are analyzing provenance data from a complex workflow consisting of numerous tasks."""

def generate_pandas_code_prompt(query: str, dynamic_schema, example_values):
    prompt = f"""
     You are a Workflow Provenance Data Science Expert that knows to query pandas DataFrames.
    {DF_FORM}
    {JOB}
    {ROLE}
    {get_df_schema_prompt(dynamic_schema, example_values)}
    ### 3. Query Interpretation Guidelines

    - Use `df` as the base DataFrame.
    - Use `activity_id` to filter by task type (valid values = schema keys).
    - Use `used.` for parameters (inputs) and `generated.` for outputs (metrics).
    - Use `telemetry_summary.duration_sec` for performance-related questions.
    - Use `hostname` when user mentions *where* a task ran.
    - Use `agent_id` when the user refers to agents (non-null means task was agent-run).

    ### 4. Hard Constraints (obey strictly)

    - Always return code in the form `result = df[<filter>][[...]]` or `result = df.loc[<filter>, [...]]`
     -THERE ARE NOT INDIVIDUAL FIELDS NAMED `used` OR `generated`, they are ONLY are prefixes to the field names.
    
    - **When filtering by `activity_id`, only select columns that belong to that activity’s schema.**
      - Use only `used.` and `generated.` fields listed in the schema for that `activity_id`.
     - Explicitly list the selected columns — **never return all columns**
    - **Only include telemetry columns if used in the query logic.**
      -THERE IS NOT A FIELD NAMED `telemetry_summary.start_time` or `telemetry_summary.end_time` or `used.start_time` or `used.end_time`. Use `started_at` and `ended_at` instead when you want to find the duration of a task, activity, or workflow execution.
      -THE GENERATED FIELDS ARE LABELED AS SUCH: `generated.()` NOT `generated_output`. Any reference to `generated_output` is incorrect and should be replaced with `generated.` prefix.
      -THERE IS NOT A FIELD NAMED `execution_id` or `used.execution_id`. Look at the QUERY to decide what correct _id field to use. Any mentions of workflow use `workflow_id`. Any mentions of task use `task_id`. Any mentions of activity use `activity_id`.
      -DO NOT USE `nlargest` in the query code, use `sort_values` instead. The `nlargest` method is not supported by the DataFrame used in this workflow.
      -An activity with a value in the `generated.` column created that value. Whereas an activity that has a value in the `used.` column used that value from another activity. IF THE `used.` and `generated.` fields share the same letter after the dot, that means that the activity associated with the `generated.` was created by another activity and the one with `used.` used that SAME value that was created by the activity with that same value in the `generated.` field.
      -WHEN calculating total time of a workflow execution (identified by `workflow_id`), get its latest task's `ended_at` and its earliest task's `started_at`and compute the difference between them.
      -WHEN user requests duration or execution time per task or for individual tasks, utilize `telemetry_summary.duration_sec`. 
      -WHEN user requests execution time per activity within workflows compute durations using the difference between the last `ended_at` and the first `started_at` grouping by activitiy_id, workflow_id rather than using `telemetry_summary.duration_sec`.
      -WHEN the user requests the first or last workflow executions, USE the `started_at` or `ended_at` field to sort the DataFrame and select the first or last rows accordingly. Do not use the `workflow_id` to determine the first or last workflow execution.
      -WHEN the user requests the "first workflow", you must identify the workflow by using workflow_id of the task with the earliest started_at. DO NOT use the smallest workflow_id. To find "last workflow" use the latest started_at.
      -WHEN the user requests a "summary" of activites, you must incorporate relevant summary statistics such as min, max, and mean, into the code you generate.
      -Do not use  df['workflow_id'].max() or  df['workflow_id'].min() to find the first or last workflow execution. Instead, use the `started_at` or `ended_at` fields to determine the first or last workflow execution.
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

    THE OUTPUT MUST BE ONE LINE OF VALID PYTHON CODE ONLY, DO NOT SAY ANYTHING ELSE.

    Strictly follow the constraints above.

    User Query:
    {query}
    """
    return prompt


def dataframe_summarizer_context(code, reduced_df, query) -> str:
    prompt = f"""
    You are a Workflow Provenance Specialist analyzing a DataFrame that was obtained to answer a query. Given:
    
    **User Query**:  
    {query}
    
    **Query_Code**:  
    {code}
    
    **Reduced DataFrame** (rows sampled from full result):  
    {reduced_df}
    
    Your task is to:
    1. Analyze the DataFrame values and columns for any meaningful or notable information.
    2. Compare the query_code with the data content to understand what the result represents. THIS IS A REDUCED DATAFRAME, the original dataframe, used to answer the query, may be much bigger. IT IS ALREADY KNOWN! Do not need to restate this.
    3. Provide a concise and direct answer to the user query. Your final response to the query should be  within ```text .

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
    
    ONCE AGAIN, ONLY PRODUCE THE PYTHON CODE. DO NOT SAY ANYTHING ELSE!
    
    User message:
    {raw_text}
    """
    return prompt
