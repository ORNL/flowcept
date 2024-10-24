"""Utilities."""

from datetime import datetime, timedelta
import json
from time import time, sleep
from typing import Callable
import os
import platform
import subprocess

import numpy as np

import flowcept.commons
from flowcept.configs import (
    PERF_LOG,
    SETTINGS_PATH,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.flowcept_dataclasses.task_object import Status


def get_utc_now() -> float:
    """Get UTC time."""
    now = datetime.utcnow()
    return now.timestamp()


def get_utc_now_str() -> str:
    """Get UTC string."""
    format_string = "%Y-%m-%dT%H:%M:%S.%f"
    now = datetime.utcnow()
    return now.strftime(format_string)


def get_utc_minutes_ago(minutes_ago=1):
    """Get UTC minutes."""
    now = datetime.utcnow()
    rounded = now - timedelta(
        minutes=now.minute % minutes_ago + minutes_ago,
        seconds=now.second,
        microseconds=now.microsecond,
    )
    return rounded.timestamp()


def perf_log(func_name, t0: float):
    """Configure the performance log."""
    if PERF_LOG:
        t1 = time()
        logger = FlowceptLogger()
        logger.debug(f"[PERFEVAL][{func_name}]={t1 - t0}")
        return t1
    return None


def get_status_from_str(status_str: str) -> Status:
    """Get the status."""
    # TODO: complete this utility function
    if status_str.lower() in {"finished"}:
        return Status.FINISHED
    elif status_str.lower() in {"created"}:
        return Status.SUBMITTED
    else:
        return Status.UNKNOWN


def get_adapter_exception_msg(adapter_kind):
    """Get the adapter."""
    return (
        f"You have an adapter for {adapter_kind} in"
        f" {SETTINGS_PATH} but we couldn't import its interceptor."
        f" Consider fixing the following exception (e.g., try installing the"
        f" adapter requirements -- see the README file remove that adapter"
        f" from the settings."
        f" Exception:"
    )


def assert_by_querying_tasks_until(
    filter,
    condition_to_evaluate: Callable = None,
    max_trials=30,
    max_time=60,
):
    """Assert by query."""
    from flowcept.flowcept_api.task_query_api import TaskQueryAPI

    query_api = TaskQueryAPI()
    start_time = time()
    trials = 0

    while (time() - start_time) < max_time and trials < max_trials:
        docs = query_api.query(filter)
        if condition_to_evaluate is None:
            if docs is not None and len(docs):
                flowcept.commons.logger.debug("Query conditions have been met! :D")
                return True
        else:
            try:
                if condition_to_evaluate(docs):
                    flowcept.commons.logger.debug("Query conditions have been met! :D")
                    return True
            except Exception:
                pass

        trials += 1
        flowcept.commons.logger.debug(
            f"Task Query condition not yet met. Trials={trials}/{max_trials}."
        )
        sleep(1)
    flowcept.commons.logger.debug(
        "We couldn't meet the query conditions after all trials or timeout! :("
    )
    return False


def chunked(iterable, size):
    """Chunk it."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


# TODO: consider reusing this function in the function assert_by_querying_task_collections_until
def evaluate_until(evaluation_condition: Callable, max_trials=30, max_time=60, msg=""):
    """Evaluate something."""
    start_time = time()
    trials = 0

    while trials < max_trials and (time() - start_time) < max_time:
        if evaluation_condition():
            return True  # Condition met

        trials += 1
        flowcept.commons.logger.debug(f"Condition not yet met. Trials={trials}/{max_trials}. {msg}")
        sleep(1)

    return False  # Condition not met within max_trials or max_time


class GenericJSONEncoder(json.JSONEncoder):
    """JSON encoder class."""

    def default(self, obj):
        """Run the default method."""
        if isinstance(obj, (list, tuple)):
            return [self.default(item) for item in obj]
        elif isinstance(obj, dict):
            return {self.default(key): self.default(value) for key, value in obj.items()}
        elif hasattr(obj, "__dict__"):
            return self.default(obj.__dict__)
        elif isinstance(obj, object):
            try:
                return str(obj)
            except Exception:
                return None
        elif isinstance(obj, np.int) or isinstance(obj, np.int32) or isinstance(obj, np.int64):
            return int(obj)
        elif (
            isinstance(obj, np.float) or isinstance(obj, np.float32) or isinstance(obj, np.float64)
        ):
            return float(obj)
        return super().default(obj)


def replace_non_serializable(obj):
    """Replace it."""
    if isinstance(obj, (int, float, bool, str, list, tuple, dict, type(None))):
        if isinstance(obj, dict):
            return {key: replace_non_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [replace_non_serializable(item) for item in obj]
        else:
            return obj
    else:
        # Replace non-serializable values with id()
        return f"{obj.__class__.__name__}_instance_id_{id(obj)}"


def get_gpu_vendor():
    """Get GPU vendor."""
    system = platform.system()

    # Linux
    if system == "Linux":
        # Check for NVIDIA GPU
        if os.path.exists("/proc/driver/nvidia/version"):
            return "NVIDIA"

        # Check for AMD GPU using lspci
        try:
            lspci_output = subprocess.check_output("lspci", shell=True).decode()
            if "AMD" in lspci_output:
                return "AMD"
        except subprocess.CalledProcessError:
            pass

    # Windows
    elif system == "Windows":
        try:
            wmic_output = subprocess.check_output(
                "wmic path win32_videocontroller get name", shell=True
            ).decode()
            if "NVIDIA" in wmic_output:
                return "NVIDIA"
            elif "AMD" in wmic_output:
                return "AMD"
        except subprocess.CalledProcessError:
            pass

    # macOS
    elif system == "Darwin":  # macOS is "Darwin" in platform.system()
        try:
            sp_output = subprocess.check_output(
                "system_profiler SPDisplaysDataType", shell=True
            ).decode()
            if "NVIDIA" in sp_output:
                return "NVIDIA"
            elif "AMD" in sp_output:
                return "AMD"
        except subprocess.CalledProcessError:
            pass

    return None


class GenericJSONDecoder(json.JSONDecoder):
    """JSON decoder class."""

    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(self, object_hook=self.object_hook, *args, **kwargs)

    def object_hook(self, dct):
        """Get object hook."""
        if "__class__" in dct:
            class_name = dct.pop("__class__")
            module_name = dct.pop("__module__")
            module = __import__(module_name)
            class_ = getattr(module, class_name)
            args = {}
            for key, value in dct.items():
                args[key] = self.object_hook(value)
            inst = class_(**args)
        else:
            inst = dct
        return inst
