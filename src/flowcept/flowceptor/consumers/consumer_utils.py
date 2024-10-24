"""Consumer utilities module."""

from typing import List, Dict
from flowcept.commons.flowcept_dataclasses.task_object import TaskObject


def curate_task_msg(task_msg_dict: dict):
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


def remove_empty_fields_from_dict(obj: dict):
    """Remove empty fields from a dictionary recursively."""
    for key, value in list(obj.items()):
        if isinstance(value, dict):
            remove_empty_fields_from_dict(value)
            if value is None:
                del obj[key]
        elif value in (None, ""):
            del obj[key]


def curate_dict_task_messages(
    doc_list: List[Dict], indexing_key: str, utc_time_at_insertion: float = 0
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
    for doc in doc_list:
        if (len(doc) == 1) and (indexing_key in doc) and (doc[indexing_key] in indexed_buffer):
            # This task_msg does not add any metadata
            continue

        # Reformatting the task msg so to append statuses, as updating them was
        # causing inconsistencies in the DB.
        if "status" in doc:
            doc[doc["status"].lower()] = True
            # doc.pop("status")

        if utc_time_at_insertion > 0:
            doc["utc_time_at_insertion"] = utc_time_at_insertion

        curate_task_msg(doc)
        indexing_key_value = doc[indexing_key]

        if indexing_key_value not in indexed_buffer:
            indexed_buffer[indexing_key_value] = doc
            continue

        for field in TaskObject.get_dict_field_names():
            if field in doc:
                if doc[field] is not None and len(doc[field]):
                    if field in indexed_buffer[indexing_key_value]:
                        indexed_buffer[indexing_key_value][field].update(doc[field])
                    else:
                        indexed_buffer[indexing_key_value][field] = doc[field]
                doc.pop(field)
        indexed_buffer[indexing_key_value].update(**doc)
    return indexed_buffer
