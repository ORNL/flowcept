from datetime import datetime
from typing import Dict, List
import copy
from collections import defaultdict
from typing import Any

import pytz


def summarize_telemetry(task: Dict, logger) -> Dict:
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

    tel_funcs = {
        "cpu": extract_cpu_info,
        "disk": extract_disk_info,
        "memory": extract_mem_info,
        "network": extract_network_info,
    }

    start_tele = task.get("telemetry_at_start", {})
    end_tele = task.get("telemetry_at_end", {})

    telemetry_summary = {}

    try:
        started_at = task.get("started_at", None)
        ended_at = task.get("ended_at", None)
        if started_at is None or ended_at is None:
            logger.warning(f"We can't summarize telemetry for duration_sec for task {task}")
        else:
            duration = ended_at - started_at
            telemetry_summary["duration_sec"] = duration
    except Exception as e:
        logger.error(f"Error to summarize telemetry for duration_sec in {task}")
        logger.exception(e)

    for key in start_tele.keys():
        try:
            if key not in tel_funcs:
                continue
            func = tel_funcs[key]
            if key in end_tele:
                telemetry_summary[key] = func(start_tele[key], end_tele[key])
            else:
                logger.warning(
                    f"We can't summarize telemetry {key} for task {task} because the key is not in the end_tele"
                )
        except Exception as e:
            logger.warning(f"Error to summarize telemetry for {key} for task {task}. Exception: {e}")
            logger.exception(e)

    return telemetry_summary


def _safe_get(task, key):
    try:
        return task.get(key)
    except Exception:
        return None


def summarize_task(task: Dict, thresholds: Dict = None, logger=None) -> Dict:
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
    task_summary = {}

    # Keys that can be copied directly
    for key in [
        "workflow_id",
        "task_id",
        "parent_task_id",
        "activity_id",
        "used",
        "generated",
        "hostname",
        "status",
        "agent_id",
        "campaign_id",
        "subtype",
    ]:
        value = _safe_get(task, key)
        if value is not None:
            if "_id" in key:
                task_summary[key] = str(value)
            else:
                task_summary[key] = value

    # Adding image column if data is image. This is to handle special cases when there is an image associated to
    # a provenance task.
    if "data" in task:
        if "custom_metadata" in task:
            if "image" in task["custom_metadata"].get("mime_type", ""):
                task_summary["image"] = task["data"]

    # Special handling for timestamp field
    try:
        time_keys = ["started_at", "ended_at"]
        for time_key in time_keys:
            timestamp = _safe_get(task, time_key)
            if timestamp is not None:
                task_summary[time_key] = datetime.fromtimestamp(timestamp, pytz.utc)
    except Exception as e:
        if logger:
            logger.exception(f"Error {e} converting timestamp for task {task.get('task_id', 'unknown')}")

    try:
        telemetry_summary = summarize_telemetry(task, logger)
        try:
            tags = tag_critical_task(
                generated=task.get("generated", {}), telemetry_summary=telemetry_summary, thresholds=thresholds
            )
            if tags:
                task_summary["tags"] = tags
        except Exception as e:
            logger.exception(e)
        task_summary["telemetry_summary"] = telemetry_summary
    except Exception as e:
        if logger:
            logger.exception(e)
        else:
            print(e)

    return task_summary


def tag_critical_task(
    generated: Dict, telemetry_summary: Dict, generated_keywords: List[str] = ["result"], thresholds: Dict = None
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

    cpu = abs(telemetry_summary.get("cpu", {}).get("percent_all_diff", 0))
    mem = telemetry_summary.get("mem", {}).get("used_mem_diff", 0)
    disk = telemetry_summary.get("disk", {}).get("read_bytes_diff", 0) + telemetry_summary.get("disk", {}).get(
        "write_bytes_diff", 0
    )
    # TODO gpu
    duration = telemetry_summary.get("duration_sec", 0)

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


sample_tasks = [
    {
        "task_id": "t1",
        "activity_id": "train_model",
        "used": {
            "dataset": {"name": "MNIST", "size": 60000, "source": {"url": "http://example.com/mnist", "format": "csv"}},
            "params": {"epochs": 5, "batch_size": 32, "shuffle": True},
        },
        "generated": {"model": {"accuracy": 0.98, "layers": [64, 64, 10], "saved_path": "/models/mnist_v1.pth"}},
        "telemetry_summary": {"duration_sec": 42.7, "cpu_percent": 85.2},
    },
    {
        "task_id": "t2",
        "activity_id": "train_model",
        "used": {
            "dataset": {
                "name": "CIFAR-10",
                "size": 50000,
                "source": {"url": "http://example.com/cifar", "format": "jpeg"},
            },
            "params": {"epochs": 10, "batch_size": 64, "shuffle": False},
        },
        "generated": {"model": {"accuracy": 0.91, "layers": [128, 128, 10], "saved_path": "/models/cifar_v1.pth"}},
        "telemetry_summary": {"duration_sec": 120.5, "cpu_percent": 92.0},
    },
    {
        "task_id": "t3",
        "activity_id": "evaluate_model",
        "used": {"model_path": "/models/mnist_v1.pth", "test_data": {"name": "MNIST-test", "samples": 10000}},
        "generated": {"metrics": {"accuracy": 0.97, "confusion_matrix": [[8500, 100], [50, 1350]]}},
        "telemetry_summary": {"duration_sec": 15.3},
    },
    {
        "task_id": "t4",
        "activity_id": "evaluate_model",
        "used": {"model_path": "/models/cifar_v1.pth", "test_data": {"name": "CIFAR-test", "samples": 10000}},
        "generated": {"metrics": {"accuracy": 0.88, "confusion_matrix": [[4000, 500], [300, 5200]]}},
        "telemetry_summary": {"duration_sec": 18.9},
    },
]


def infer_dtype(value: Any) -> str:
    """Infer a simplified dtype label for the value."""
    if isinstance(value, bool):
        return "bool"
    elif isinstance(value, int):
        return "int"
    elif isinstance(value, float):
        return "float"
    elif isinstance(value, str):
        return "str"
    elif isinstance(value, list):
        return "list"
    return "str"  # fallback for other types


def flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Recursively flatten nested dicts using dot notation."""
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def update_schema(schema_section: list, flat_fields: dict):
    """Update schema section with flattened fields and example values."""
    field_map = {f["n"]: f for f in schema_section}

    for key, value in flat_fields.items():
        dtype = infer_dtype(value)
        if isinstance(value, float):
            val_repr = round(value, 2)
        elif isinstance(value, (dict, list)):
            val_repr = str(value)
        else:
            val_repr = value

        if isinstance(val_repr, str) and len(val_repr) > 100:
            val_repr = val_repr[:100] + "#TRUNCATED"

        if key not in field_map:
            field = {
                "n": key,
                "d": dtype,
                "v": [val_repr] if val_repr is not None else [],
            }
            schema_section.append(field)
            field_map[key] = field
        else:
            field = field_map[key]
            if val_repr not in field["v"] and len(field["v"]) < 3:
                field["v"].append(val_repr)


def update_tasks_summary_schema(tasks: list[dict], schema) -> dict:
    """Update tasks_summary schema."""
    act_schema = update_activity_schema(tasks)
    merged_schema = deep_merge_dicts(act_schema, schema)
    return merged_schema


def update_activity_schema(tasks: list[dict]) -> dict:
    """Build schema for each activity_id from list of task dicts."""
    schema = defaultdict(
        lambda: {
            "in": [],
            "out": [],
            # "tel": [],
        }
    )

    for task in tasks:
        activity_id = task.get("activity_id")
        if not activity_id:
            continue

        activity_schema = schema[activity_id]

        for section_key, schema_key in [
            ("used", "in"),
            ("generated", "out"),
            #   ("telemetry_summary", "tel"),
        ]:
            section_data = task.get(section_key)
            if isinstance(section_data, dict):
                flat_fields = flatten_dict(section_data, parent_key=section_key)
                update_schema(activity_schema[schema_key], flat_fields)

    schema = dict(schema)
    return schema


def deep_merge_dicts(a: dict, b: dict) -> dict:
    """
    Recursively merge dict b into dict a:
    - Does not overwrite existing values in a.
    - If both values are dicts, merges recursively.
    - If both values are lists, concatenates and deduplicates.
    - Otherwise, keeps value from a.
    Returns a new dict (does not mutate inputs).
    """
    result = copy.deepcopy(a)

    for key, b_val in b.items():
        if key not in result:
            result[key] = copy.deepcopy(b_val)
        else:
            a_val = result[key]
            if isinstance(a_val, dict) and isinstance(b_val, dict):
                result[key] = deep_merge_dicts(a_val, b_val)
            elif isinstance(a_val, list) and isinstance(b_val, list):
                combined = a_val + [item for item in b_val if item not in a_val]
                result[key] = combined
            # preserve a_val otherwise
    return result
