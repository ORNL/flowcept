"""
The base of this code was generated using ChatGPT.

Prompt:

Here I have a list containing one real task.

<Paste one real task here>

I want to create a list of summarized task data, per task, containing:
- activity_id
- task_id
- used
- generated
- task_duration (ended_at - started_at)
- hostname
- cpu_info
- disk_info
- mem_info
- network_info
<Consider adding GPU info too, if you have gpu in your task data>

Where info about cpu, disk, mem, and network must consider telemetry_at_end and telemetry_at_start.

We will use this summarized data as input for LLM questions to find patterns in the resource usage and how they relate
to input (used) and output (generated) of each task.
"""

from typing import Dict, List


def summarize_telemetry(task: Dict) -> Dict:
    """
    Extract and compute the telemetry summary for a task based on start and end telemetry snapshots.

    Parameters
    ----------
    task : dict
        The task dictionary containing telemetry_at_start and telemetry_at_end.

    Returns
    -------
    dict
        A summary of telemetry differences including CPU, disk, memory, and network metrics, and task duration.
    """

    def extract_cpu_info(start: Dict, end: Dict) -> Dict:
        return {
            "percent_all_diff": end["percent_all"] - start["percent_all"],
            "user_time_diff": end["times_avg"]["user"] - start["times_avg"]["user"],
            "system_time_diff": end["times_avg"]["system"] - start["times_avg"]["system"],
            "idle_time_diff": end["times_avg"]["idle"] - start["times_avg"]["idle"],
        }

    def extract_disk_info(start: Dict, end: Dict) -> Dict:
        io_start = start["io_sum"]
        io_end = end["io_sum"]
        return {
            "read_bytes_diff": io_end["read_bytes"] - io_start["read_bytes"],
            "write_bytes_diff": io_end["write_bytes"] - io_start["write_bytes"],
            "read_count_diff": io_end["read_count"] - io_start["read_count"],
            "write_count_diff": io_end["write_count"] - io_start["write_count"],
        }

    def extract_mem_info(start: Dict, end: Dict) -> Dict:
        return {
            "used_mem_diff": end["virtual"]["used"] - start["virtual"]["used"],
            "percent_diff": end["virtual"]["percent"] - start["virtual"]["percent"],
            "swap_used_diff": end["swap"]["used"] - start["swap"]["used"],
        }

    def extract_network_info(start: Dict, end: Dict) -> Dict:
        net_start = start["netio_sum"]
        net_end = end["netio_sum"]
        return {
            "bytes_sent_diff": net_end["bytes_sent"] - net_start["bytes_sent"],
            "bytes_recv_diff": net_end["bytes_recv"] - net_start["bytes_recv"],
            "packets_sent_diff": net_end["packets_sent"] - net_start["packets_sent"],
            "packets_recv_diff": net_end["packets_recv"] - net_start["packets_recv"],
        }

    start_tele = task["telemetry_at_start"]
    end_tele = task["telemetry_at_end"]

    started_at = task["started_at"]
    ended_at = task["ended_at"]
    duration = ended_at - started_at

    telemetry_summary = {
        "duration_sec": duration,
        "cpu_info": extract_cpu_info(start_tele["cpu"], end_tele["cpu"]),
        "disk_info": extract_disk_info(start_tele["disk"], end_tele["disk"]),
        "mem_info": extract_mem_info(start_tele["memory"], end_tele["memory"]),
        "network_info": extract_network_info(start_tele["network"], end_tele["network"]),
    }

    return telemetry_summary


def summarize_task(task: Dict, thresholds: Dict = None) -> Dict:
    """
    Summarize key metadata and telemetry for a task, optionally tagging critical conditions.

    Parameters
    ----------
    task : dict
        The task dictionary containing metadata and telemetry snapshots.
    thresholds : dict, optional
        Threshold values used to tag abnormal resource usage.

    Returns
    -------
    dict
        Summary of the task including identifiers, telemetry summary, and optional critical tags.
    """
    telemetry_summary = summarize_telemetry(task)
    task_summary = {
        "workflow_id": task.get("workflow_id"),
        "task_id": task.get("task_id"),
        "activity_id": task.get("activity_id"),
        "used": task.get("used"),
        "generated": task.get("generated"),
        "hostname": task.get("hostname"),
        "status": task.get("status"),
        "telemetry_summary": telemetry_summary,
    }

    tags = tag_critical_task(
        generated=task.get("generated", {}),
        telemetry_summary=telemetry_summary,
        thresholds=thresholds
    )
    if tags:
        task_summary["tags"] = tags

    return task_summary


def tag_critical_task(
    generated: Dict,
    telemetry_summary: Dict,
    generated_keywords: List[str] = ['result'],
    thresholds: Dict = None
) -> List[str]:
    """
    Tag a task with labels indicating abnormal or noteworthy resource usage or result anomalies.

    Parameters
    ----------
    generated : dict
        Dictionary of generated output values (e.g., results).
    telemetry_summary : dict
        Telemetry summary produced from summarize_telemetry().
    generated_keywords : list of str, optional
        List of keys in the generated output to check for anomalies.
    thresholds : dict, optional
        Custom thresholds for tagging high CPU, memory, disk, etc.

    Returns
    -------
    list of str
        Tags indicating abnormal patterns (e.g., "high_cpu", "low_output").
    """
    if thresholds is None:
        thresholds = {
            "high_cpu": 80,
            "high_mem": 1e9,
            "high_disk": 1e8,
            "long_duration": 0.8,
            "low_output": 0.1,
            "high_output": 0.9,
        }

    cpu = abs(telemetry_summary["cpu_info"].get("percent_all_diff", 0))
    mem = telemetry_summary["mem_info"].get("used_mem_diff", 0)
    disk = (
        telemetry_summary["disk_info"].get("read_bytes_diff", 0)
        + telemetry_summary["disk_info"].get("write_bytes_diff", 0)
    )
    duration = telemetry_summary["duration_sec"]

    tags = []

    if cpu > thresholds["high_cpu"]:
        tags.append("high_cpu")
    if mem > thresholds["high_mem"]:
        tags.append("high_mem")
    if disk > thresholds["high_disk"]:
        tags.append("high_disk")
    if duration > thresholds["long_duration"]:
        tags.append("long_duration")

    for key in generated_keywords:
        value = generated.get(key, 0)
        if value < thresholds["low_output"]:
            tags.append("low_output")
        if value > thresholds["high_output"]:
            tags.append("high_output")

    return tags
