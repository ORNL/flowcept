from datetime import datetime


def get_utc_now() -> float:
    now = datetime.utcnow()
    return now.timestamp()
