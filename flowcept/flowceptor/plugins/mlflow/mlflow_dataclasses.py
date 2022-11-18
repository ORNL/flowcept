from dataclasses import dataclass


@dataclass
class RunData:

    run_uuid: str
    start_time: int
    end_time: int
    metrics: dict
    parameters: dict
    status: str
