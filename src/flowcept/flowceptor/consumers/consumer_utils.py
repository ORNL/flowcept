"""Consumer utilities module."""

from datetime import datetime
from zoneinfo import ZoneInfo
from time import time
from typing import List, Dict

from flowcept.commons.flowcept_dataclasses.task_object import TaskObject
from flowcept.commons.vocabulary import Status

UTC_TZ = ZoneInfo("UTC")


def curate_task_msg(task_msg_dict: dict, convert_times=True, keys_to_drop: List = None):
    """Curate a task message."""
    # Converting any arg to kwarg in the form {"arg1": val1, "arg2: val2}
    for field in TaskObject.get_dict_field_names():
        if field not in task_msg_dict:
            continue
        field_val = task_msg_dict[field]
        if type(field_val) is dict and not field_val:
            task_msg_dict.pop(field)  # removing empty fields
            continue

        if type(field_val) is dict:
            original_field_val = field_val.copy()
            for k in original_field_val:
                if type(original_field_val[k]) is dict and not original_field_val[k]:
                    field_val.pop(k)  # removing inner empty fields
            field_val = convert_keys_to_strings(field_val)
            task_msg_dict[field] = field_val
        else:
            field_val_dict = {}
            if type(field_val) in [list, tuple]:
                i = 0
                for arg in field_val:
                    field_val_dict[f"arg{i}"] = arg
                    i += 1
            else:  # Scalar value
                field_val_dict["arg0"] = field_val
            task_msg_dict[field] = field_val_dict

    # Moving 'workflow_id' to the right place if it's in the 'used' field.
    # This happens because of the @lightweight_flowcept_task
    if "used" in task_msg_dict and task_msg_dict["used"].get("workflow_id", None):
        task_msg_dict["workflow_id"] = task_msg_dict["used"].pop("workflow_id")

    if keys_to_drop is not None:
        for k in keys_to_drop:
            task_msg_dict.pop(k, None)

    if convert_times:
        for time_field in TaskObject.get_time_field_names():
            if time_field in task_msg_dict:
                task_msg_dict[time_field] = datetime.fromtimestamp(task_msg_dict[time_field], UTC_TZ)

        if "registered_at" not in task_msg_dict:
            task_msg_dict["registered_at"] = datetime.fromtimestamp(time(), UTC_TZ)


def remove_empty_fields_from_dict(obj: dict):
    """Remove empty fields from a dictionary recursively."""
    for key, value in list(obj.items()):
        if isinstance(value, dict):
            remove_empty_fields_from_dict(value)
            if value is None:
                del obj[key]
        elif value in (None, ""):
            del obj[key]


def convert_keys_to_strings(obj):
    """
    Recursively converts all dictionary keys to strings.

    Parameters
    ----------
    obj : dict, list, or any
        The input object, which can be a dictionary, list, or any other data type.

    Returns
    -------
    dict, list, or any
        The transformed object where all dictionary keys are converted to strings.
        Lists and other values remain unchanged.

    Examples
    --------
    >>> convert_keys_to_strings({1: "a", 2: {"nested": 3}})
    {'1': 'a', '2': {'nested': 3}}

    >>> convert_keys_to_strings([{"key": 123}, {456: "value"}])
    [{'key': 123}, {'456': 'value'}]
    """
    if isinstance(obj, dict):
        return {str(k): convert_keys_to_strings(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_keys_to_strings(i) for i in obj]
    else:
        return obj


def curate_dict_task_messages(
    doc_list: List[Dict],
    indexing_key: str,
    utc_time_at_insertion: float = 0,
    convert_times=True,
    keys_to_drop: List = None,
):
    """Remove duplicates.

    This function removes duplicates based on the indexing_key (e.g., task_id)
    locally before sending to MongoDB.

    It also avoids tasks changing states once they go into finished state.
    This is needed because we can't guarantee MQ orders.

    Finished states have higher priority in status changes, as we don't expect
    a status change once a task goes into finished state.

    It also resolves updates (instead of replacement) of inner nested fields
    in a JSON object.

    :param doc_list:
    :param indexing_key: #the key we want to index. E.g., task_id in tasks collection
    :return:
    """
    indexed_buffer = {}
    for doc_ref in doc_list:
        if (len(doc_ref) == 1) and (indexing_key in doc_ref) and (doc_ref[indexing_key] in indexed_buffer):
            # This task_msg does not add any metadata
            continue
        doc = doc_ref.copy()
        # Reformatting the task msg so to append statuses, as updating them was
        # causing inconsistencies in the DB.
        if "status" in doc:
            doc[doc["status"].lower()] = True
            # doc.pop("status")
            if "finished" in doc and doc["finished"]:
                doc["status"] = Status.FINISHED.value

        if utc_time_at_insertion > 0:
            doc["utc_time_at_insertion"] = utc_time_at_insertion

        curate_task_msg(doc, convert_times, keys_to_drop)
        indexing_key_value = doc[indexing_key]

        if indexing_key_value not in indexed_buffer:
            indexed_buffer[indexing_key_value] = doc
            continue

        for field in TaskObject.get_dict_field_names():
            if field in doc:
                if doc[field] is not None and len(doc[field]):
                    doc[field] = convert_keys_to_strings(doc[field])
                    if field in indexed_buffer[indexing_key_value]:
                        indexed_buffer[indexing_key_value][field].update(doc[field])
                    else:
                        indexed_buffer[indexing_key_value][field] = doc[field]
                doc.pop(field)

        indexed_buffer[indexing_key_value].update(**doc)
    return indexed_buffer
