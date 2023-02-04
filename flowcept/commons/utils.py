from datetime import datetime

from flowcept.commons.flowcept_data_classes import Status


def get_utc_now() -> float:
    now = datetime.utcnow()
    return now.timestamp()


def get_status_from_str(status_str: str) -> Status:
    # TODO: complete this utility function
    if status_str.lower() in {"finished"}:
        return Status.FINISHED
    elif status_str.lower() in {"created"}:
        return Status.SUBMITTED
    else:
        return Status.UNKNOWN
