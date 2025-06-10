from mcp.server.fastmcp.prompts import base

BASE_ROLE = "You are a helpful assistant analyzing provenance data from a large-scale workflow composed of multiple tasks. "
DATA_SCHEMA_PROMPT = (
    "A task object has its task provenance, i.e., input data stored in 'used' field and output data stored in the 'generated' field "
    "Tasks with a same 'workflow_id' means that they belong to the same workflow execution trace. "
    "Please notice the 'tags' field, as they may indicate critical tasks. "
    "The 'telemetry_summary' field holds how much resources (CPU, disk, memory, network) each task consumed, along with its duration in seconds (duration_sec). We also know about its scheduling (or placement) as we store in 'hostname' field the compute node name where it ran. ")

QUESTION_PROMPT = "I am particularly more interested in the following question: %QUESTION%."

def get_question_prompt(question):
    return base.UserMessage(QUESTION_PROMPT.replace("%QUESTION%", question))

SINGLE_TASK_PROMPT = {
    "role": f"{BASE_ROLE}. You are focusing now on a particular task object which I will provide below. ",
    "data_schema": DATA_SCHEMA_PROMPT,
    "job": "Your job is to analyze this single task.  Find any anomalies, relationships, or correlations between input, output, "
           "resource usage metrics, task duration, and task placement. "
           "Interesting relationships or correlations that involve used vs generated data are particularly more important. "
           "Interesting Relationships or correlations between (used or generated) vs any resource usage metric are also very important. "
           "Please highlight any outliers or critical information and provide actionable insights or recommendations. "
           "Explain what this task may be doing. Use the data provided to explain your responses. "
}
MULTITASK_PROMPTS = {
    "role": "You are a helpful assistant analyzing provenance data from a large-scale workflow composed of multiple tasks. ",
    "data_schema": DATA_SCHEMA_PROMPT,
    "job": "Your job is to analyze a list of task objects to find patterns across tasks, anomalies, relationships, or correlations between input, output, "
           "resource usage metrics, task duration, and task placement. "
           "Interesting relationships or correlations that involve used vs generated data are particularly more important. "
           "Interesting Relationships or correlations between (used or generated) vs any resource usage metric are also very important. "
           "Explain what this workflow is about or what you think its purpose is. "
           "Please highlight any outliers or critical tasks and provide actionable insights or recommendations. "
           "Use the data provided to explain your responses. "
}
BASE_MULTITASK_PROMPT = [base.UserMessage(MULTITASK_PROMPTS[k]) for k in ["role", "data_schema", "job"]]
BASE_SINGLETASK_PROMPT = [base.UserMessage(SINGLE_TASK_PROMPT[k]) for k in ["role", "data_schema", "job"]]
