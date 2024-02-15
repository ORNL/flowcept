from datetime import datetime, timedelta
import json
from time import time, sleep
from typing import Callable

import numpy as np

import flowcept.commons
from flowcept.configs import (
    PERF_LOG,
    SETTINGS_PATH,
    CAMPAIGN_ID,
    FLOWCEPT_USER,
    settings,
)
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.flowcept_dataclasses.task_message import Status
from flowcept.version import __version__


def get_utc_now() -> float:
    now = datetime.utcnow()
    return now.timestamp()


def get_utc_now_str() -> str:
    format_string = "%Y-%m-%dT%H:%M:%S.%f"
    now = datetime.utcnow()
    return now.strftime(format_string)


def get_utc_minutes_ago(minutes_ago=1):
    now = datetime.utcnow()
    rounded = now - timedelta(
        minutes=now.minute % minutes_ago + minutes_ago,
        seconds=now.second,
        microseconds=now.microsecond,
    )
    return rounded.timestamp()


def perf_log(func_name, t0: float):
    if PERF_LOG:
        t1 = time()
        logger = FlowceptLogger()
        logger.debug(f"[PERFEVAL][{func_name}]={t1 - t0}")
        return t1
    return None


def get_status_from_str(status_str: str) -> Status:
    # TODO: complete this utility function
    if status_str.lower() in {"finished"}:
        return Status.FINISHED
    elif status_str.lower() in {"created"}:
        return Status.SUBMITTED
    else:
        return Status.UNKNOWN


def get_basic_workflow_info(workflow_id):
    workflow_info = {
        "workflow_id": workflow_id,
        "campaign_id": CAMPAIGN_ID,
        "utc_timestamp": get_utc_now(),
        "flowcept_user": FLOWCEPT_USER,
        "flowcept_version": __version__,
        "flowcept_settings": settings,
    }
    return workflow_info


def get_adapter_exception_msg(adapter_kind):
    return (
        f"You have an adapter for {adapter_kind} in"
        f" {SETTINGS_PATH} but we couldn't import its interceptor."
        f" Consider fixing the following exception (e.g., try installing the"
        f" adapter requirements -- see the README file remove that adapter"
        f" from the settings."
        f" Exception:"
    )


def assert_by_querying_task_collections_until(
    doc_dao,
    filter,
    condition_to_evaluate: Callable = None,
    max_trials=30,
    max_time=60,
):
    start_time = time()
    trials = 0

    while (time() - start_time) < max_time and trials < max_trials:
        docs = doc_dao.task_query(filter)
        if condition_to_evaluate is None:
            if docs is not None and len(docs):
                return True
        else:
            try:
                if condition_to_evaluate(docs):
                    return True
            except:
                pass

        trials += 1
        flowcept.commons.logger.debug(
            f"Task Query condition not yet met. Trials={trials}/{max_trials}."
        )
        sleep(1)

    return False


# TODO: consider reusing this function in the function assert_by_querying_task_collections_until
def evaluate_until(
    evaluation_condition: Callable, max_trials=30, max_time=60, msg=""
):
    start_time = time()
    trials = 0

    while trials < max_trials and (time() - start_time) < max_time:
        if evaluation_condition():
            return True  # Condition met

        trials += 1
        flowcept.commons.logger.debug(
            f"Condition not yet met. Trials={trials}/{max_trials}. {msg}"
        )
        sleep(1)

    return False  # Condition not met within max_trials or max_time


class GenericJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (list, tuple)):
            return [self.default(item) for item in obj]
        elif isinstance(obj, dict):
            return {
                self.default(key): self.default(value)
                for key, value in obj.items()
            }
        elif hasattr(obj, "__dict__"):
            return self.default(obj.__dict__)
        elif isinstance(obj, object):
            try:
                return str(obj)
            except:
                return None
        elif (
            isinstance(obj, np.int)
            or isinstance(obj, np.int32)
            or isinstance(obj, np.int64)
        ):
            return int(obj)
        elif (
            isinstance(obj, np.float)
            or isinstance(obj, np.float32)
            or isinstance(obj, np.float64)
        ):
            return float(obj)
        return super().default(obj)


class GenericJSONDecoder(json.JSONDecoder):
    def __init__(self, *args, **kwargs):
        json.JSONDecoder.__init__(
            self, object_hook=self.object_hook, *args, **kwargs
        )

    def object_hook(self, dct):
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
