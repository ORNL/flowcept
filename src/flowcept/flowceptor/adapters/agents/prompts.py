from mcp.server.fastmcp.prompts import base

BASE_ROLE = (
    "You are a helpful assistant analyzing provenance data from a large-scale workflow composed of multiple tasks."
)

DATA_SCHEMA_PROMPT = (
    "A task object has its provenance: input data is stored in the 'used' field, output in the 'generated' field. "
    "Tasks sharing the same 'workflow_id' belong to the same workflow execution trace. "
    "Pay attention to the 'tags' field, as it may indicate critical tasks. "
    "The 'telemetry_summary' field reports CPU, disk, memory, and network usage, along with 'duration_sec'. "
    "Task placement is stored in the 'hostname' field."
)

QUESTION_PROMPT = "I am particularly more interested in the following question: %QUESTION%."

def get_question_prompt(question: str):
    """Generates a user prompt with the given question filled in."""
    return base.UserMessage(QUESTION_PROMPT.replace("%QUESTION%", question))

SINGLE_TASK_PROMPT = {
    "role": f"{BASE_ROLE} You are focusing now on a particular task object which I will provide below.",
    "data_schema": DATA_SCHEMA_PROMPT,
    "job": (
        "Your job is to analyze this single task. Find any anomalies, relationships, or correlations between input, output, "
        "resource usage metrics, task duration, and task placement. "
        "Correlations involving 'used' vs 'generated' data are especially important. "
        "So are relationships between (used or generated) data and resource metrics. "
        "Highlight outliers or critical information and give actionable insights or recommendations. "
        "Explain what this task may be doing, using the data provided."
    )
}

MULTITASK_PROMPTS = {
    "role": BASE_ROLE,
    "data_schema": DATA_SCHEMA_PROMPT,
    "job": (
        "Your job is to analyze a list of task objects to identify patterns across tasks, anomalies, relationships,"
        " or correlations between inputs, outputs, resource usage, duration, and task placement. "
        "Correlations involving 'used' vs 'generated' data are especially important. "
        "So are relationships between (used or generated) data and resource metrics. "
        "Try to infer the purpose of the workflow. "
        "Highlight outliers or critical tasks and give actionable insights or recommendations. "
        "Use the data provided to justify your analysis."
    )
}

BASE_SINGLETASK_PROMPT = [base.UserMessage(SINGLE_TASK_PROMPT[k]) for k in ("role", "data_schema", "job")]
BASE_MULTITASK_PROMPT = [base.UserMessage(MULTITASK_PROMPTS[k]) for k in ("role", "data_schema", "job")]
