import numbers
from datetime import timedelta
from typing import List, Dict

import pandas as pd

from flowcept.commons.flowcept_dataclasses.task_message import Status


def get_doc_status(row):
    if row.get("status"):
        return row.get("status")
    elif row.get("finished"):
        return Status.FINISHED.name
    elif row.get("error"):
        return Status.ERROR.name
    elif row.get("running"):
        return Status.RUNNING.name
    elif row.get("submitted"):
        return Status.SUBMITTED.name
    else:
        return Status.UNKNOWN.name


def to_datetime(logger, df, column_name, _shift_hours=0):
    if column_name in df.columns:
        try:
            df[column_name] = pd.to_datetime(
                df[column_name], unit="s"
            ) + timedelta(hours=_shift_hours)
        except Exception as _e:
            logger.exception(_e)


def _calc_telemetry_diff_for_row(start, end):
    if isinstance(start, numbers.Number):
        return end - start
    elif type(start) == dict:
        diff_dict = {}
        for key in start:
            diff_dict[key] = _calc_telemetry_diff_for_row(
                start[key], end[key]
            )
        return diff_dict

    elif type(start) == list:
        diff_list = []
        for i in range(0, len(start)):
            diff_list.append(_calc_telemetry_diff_for_row(start[i], end[i]))
        return diff_list
    elif type(start) == str:
        return start
    else:
        raise Exception(
            "This is unexpected", start, end, type(start), type(end)
        )


def calculate_telemetry_diff_for_docs(docs: List[Dict]):
    new_docs = []
    for doc in docs:
        new_doc = doc.copy()
        telemetry_start = new_doc.get("telemetry_at_start")
        telemetry_end = new_doc.get("telemetry_at_end")
        if telemetry_start is None or telemetry_end is None:
            new_docs.append(new_doc)
            continue
        new_telemetry = dict()
        for key in telemetry_start:
            new_telemetry[key] = _calc_telemetry_diff_for_row(
                telemetry_start[key], telemetry_end[key]
            )
        new_doc["telemetry_diff"] = new_telemetry
        new_docs.append(new_doc)

    return new_docs
