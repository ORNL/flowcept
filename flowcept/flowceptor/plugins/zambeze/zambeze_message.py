from dataclasses import dataclass
from typing import List, Dict


@dataclass
class ZambezeMessage:

    name: str
    activity_id: str
    campaign_id: str
    origin_agent_id: str
    files: List[str]
    command: str
    activity_status: str
    arguments: List[str]
    kwargs: Dict
    depends_on: List[str]
