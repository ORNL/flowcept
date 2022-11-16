from dataclasses import dataclass, fields


@dataclass
class Run:

    run_uuid: str
    name: str
    user_id: str
    start_time: int
    end_time: int

    @classmethod
    @property
    def fields(cls):
        return ", ".join([field.name for field in fields(cls)])
