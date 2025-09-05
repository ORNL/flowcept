"""Utilities."""

import argparse
from datetime import datetime, timedelta, timezone
import json
from time import time, sleep
from typing import Callable
import os
import platform
import subprocess
import types
import numpy as np

from flowcept import configs
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import PERF_LOG
from flowcept.commons.vocabulary import Status


def get_utc_now() -> float:
    """Get current UTC time as a timestamp (seconds since epoch)."""
    now = datetime.now(timezone.utc)
    return now.timestamp()


def get_utc_now_str() -> str:
    """Get UTC string."""
    format_string = "%Y-%m-%dT%H:%M:%S.%f%z"
    now = datetime.now(timezone.utc)
    return now.strftime(format_string)


def datetime_to_str(dt: datetime) -> str:
    """Format a datetime object to a string in ISO-like format."""
    format_string = "%Y-%m-%dT%H:%M:%S.%f"
    return dt.strftime(format_string)


def get_utc_minutes_ago(minutes_ago=1, return_float=False):
    """Get UTC minutes ago."""
    now = datetime.now(timezone.utc)
    rounded = now - timedelta(
        minutes=now.minute % minutes_ago + minutes_ago,
        seconds=now.second,
        microseconds=now.microsecond,
    )
    if return_float:
        return rounded.timestamp()
    else:
        return rounded


def perf_log(func_name, t0: float, logger=None):
    """Configure the performance log."""
    if PERF_LOG:
        t1 = time()
        _logger = logger or FlowceptLogger()
        _logger.debug(f"[PERFEVAL][{func_name}]={t1 - t0}")
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


def assert_by_querying_tasks_until(
    filter,
    condition_to_evaluate: Callable = None,
    max_trials=10,
    max_time=60,
):
    """Assert by query."""
    from flowcept import Flowcept

    logger = FlowceptLogger()
    start_time = time()
    trials = 0
    exception = None

    while (time() - start_time) < max_time and trials < max_trials:
        docs = Flowcept.db.query(filter=filter, collection="tasks")
        if condition_to_evaluate is None:
            if docs is not None and len(docs):
                logger.debug("Query conditions have been met! :D")
                return True
        else:
            try:
                if condition_to_evaluate(docs):
                    logger.debug("Query conditions have been met! :D")
                    return True
            except Exception as e:
                exception = e
                pass

        trials += 1
        logger.debug(f"Task Query condition not yet met. Trials={trials}/{max_trials}.")
        sleep(1)

    logger.error("We couldn't meet the query conditions after all trials or timeout! :(")
    if exception is not None:
        logger.error("Last exception:")
        logger.exception(exception)
    return False


def chunked(iterable, size):
    """Chunk it."""
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


# TODO: consider reusing this function in the function assert_by_querying_task_collections_until
def evaluate_until(evaluation_condition: Callable, max_trials=30, max_time=60, msg=""):
    """Evaluate something."""
    logger = FlowceptLogger()
    start_time = time()
    trials = 0

    while trials < max_trials and (time() - start_time) < max_time:
        if evaluation_condition():
            return True  # Condition met

        trials += 1
        logger.debug(f"Condition not yet met. Trials={trials}/{max_trials}. {msg}")
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
        elif isinstance(obj, np.float) or isinstance(obj, np.float32) or isinstance(obj, np.float64):
            return float(obj)
        return super().default(obj)


def replace_non_serializable_times(obj, tz=timezone.utc):
    """Replace non-serializable datetimes in an object with ISO 8601 strings (ms precision)."""
    for time_field in TaskObject.get_time_field_names():
        if time_field in obj and isinstance(obj[time_field], datetime):
            obj[time_field] = obj[time_field].astimezone(tz).isoformat(timespec="milliseconds")


__DICT__CLASSES = (argparse.Namespace,)


def replace_non_serializable(obj):
    """Replace non-serializable items in an object."""
    if isinstance(obj, (int, float, bool, str, list, tuple, dict, type(None))):
        if isinstance(obj, dict):
            return {key: replace_non_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [replace_non_serializable(item) for item in obj]
        else:
            return obj
    else:
        if hasattr(obj, "to_flowcept_dict"):
            return obj.to_flowcept_dict()
        elif hasattr(obj, "to_dict"):
            return obj.to_dict()
        elif isinstance(obj, __DICT__CLASSES):
            return obj.__dict__
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
            wmic_output = subprocess.check_output("wmic path win32_videocontroller get name", shell=True).decode()
            if "NVIDIA" in wmic_output:
                return "NVIDIA"
            elif "AMD" in wmic_output:
                return "AMD"
        except subprocess.CalledProcessError:
            pass

    # macOS
    elif system == "Darwin":  # macOS is "Darwin" in platform.system()
        try:
            sp_output = subprocess.check_output("system_profiler SPDisplaysDataType", shell=True).decode()
            if "NVIDIA" in sp_output:
                return "NVIDIA"
            elif "AMD" in sp_output:
                return "AMD"
        except subprocess.CalledProcessError:
            pass

    return None


def get_current_config_values():
    """Get current config values."""
    _vars = {}
    for var_name in dir(configs):
        if not var_name.startswith("_"):
            val = getattr(configs, var_name)
            if not isinstance(val, types.ModuleType):
                _vars[var_name] = val
    _vars["ADAPTERS"] = list(_vars.get("ADAPTERS", []))
    return _vars


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


def get_git_info(path: str = "."):
    """Get Git Repo metadata."""
    from git import Repo

    repo = Repo(path, search_parent_directories=True)
    head = repo.head.commit.hexsha
    short = repo.git.rev_parse(head, short=True)
    branch = repo.active_branch.name if not repo.head.is_detached else "HEAD"
    remote = next(iter(repo.remotes)).url if repo.remotes else None
    dirty = "dirty" if repo.is_dirty() else "clean"
    root = repo.working_tree_dir
    return {"sha": head, "short_sha": short, "branch": branch, "root": root, "remote": remote, "dirty": dirty}


class ClassProperty:
    """Wrapper to simulate property of class methods, removed in py313."""

    def __init__(self, fget):
        self.fget = fget

    def __get__(self, instance, owner):
        return self.fget(owner)
