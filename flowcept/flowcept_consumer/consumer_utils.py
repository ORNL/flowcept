from typing import List, Dict

from flowcept.commons.flowcept_data_classes import TaskMessage, Status


def curate_task_msg(task_msg_dict: dict):
    # Converting any arg to kwarg in the form {"arg1": val1, "arg2: val2}
    for field in TaskMessage.get_dict_field_names():
        if field not in task_msg_dict:
            continue
        field_val = task_msg_dict[field]
        if not field_val:
            task_msg_dict.pop(field)  # removing empty fields
            continue
        if type(field_val) == dict:
            original_field_val = field_val.copy()
            for k in original_field_val:
                if not original_field_val[k]:
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
                field_val_dict["arg1"] = field_val
            task_msg_dict[field] = field_val_dict


def curate_dict_task_messages(
    dict_task_messages: List[Dict], indexing_key: str
):
    """
       This function removes duplicates based on the
        indexing_key (e.g., task_id) locally before sending
        to MongoDB.
        It also avoids tasks changing states once they go into finished state.
        This is needed because we can't guarantee MQ orders, and finished
        states have higher priority in status changes, as we don't expect a
        status change once a task goes into finished state.
        It also resolves updates (instead of replacement) of
        inner nested fields in a JSON object.
    :param dict_task_messages:
    :param indexing_key:
    :return:
    """
    indexed_buffer = {}
    for doc in dict_task_messages:
        if (
            (len(doc) == 1)
            and (indexing_key in doc)
            and (doc[indexing_key] in indexed_buffer)
        ):
            # This task_msg does not add any metadata
            continue

        curate_task_msg(doc)
        indexing_key_value = doc[indexing_key]
        if doc[indexing_key] not in indexed_buffer:
            indexed_buffer[indexing_key_value] = doc
            continue

        if (
            "finished" in indexed_buffer[indexing_key_value]
            and "status" in doc
        ):
            doc.pop("status")

        if "status" in doc:
            for finished_status in Status.get_finished_statuses():
                if finished_status == doc["status"]:
                    indexed_buffer[indexing_key_value]["finished"] = True

        for field in TaskMessage.get_dict_field_names():
            if field in doc:
                if doc[field] is not None and len(doc[field]):
                    if field in indexed_buffer[indexing_key_value]:
                        indexed_buffer[indexing_key_value][field].update(
                            doc[field]
                        )
                    else:
                        indexed_buffer[indexing_key_value][field] = doc[field]
                doc.pop(field)

        indexed_buffer[indexing_key_value].update(**doc)
    return indexed_buffer
