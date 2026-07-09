"""Agent Object module."""

from typing import Dict, AnyStr
import msgpack
from omegaconf import OmegaConf, DictConfig

from flowcept.commons.utils import get_utc_now
from flowcept.commons.utils import sanitize_json_like
from flowcept.configs import (
    EXTRA_METADATA,
)


class AgentObject:
    """Agent object class.

    Represents metadata and provenance details for an agent execution.
    """

    agent_id: AnyStr = None
    """Unique identifier for the agent."""

    name: AnyStr = None
    """Descriptive name for the agent."""

    user: AnyStr = None
    """User who launched or owns the agent run."""

    workflow_id: AnyStr = None
    """Workflow identifier associated with the agent."""

    campaign_id: AnyStr = None
    """Campaign identifier associated with the agent."""

    extra_metadata: Dict = None
    """Optional free-form metadata for extensions not covered by other fields."""

    def __init__(self, agent_id=None, name=None, workflow_id=None, campaign_id=None):
        self.agent_id = agent_id
        self.name = name
        self.workflow_id = workflow_id
        self.campaign_id = campaign_id
        self.registered_at = get_utc_now()

    @staticmethod
    def agent_id_field():
        """Get agent id."""
        return "agent_id"

    @staticmethod
    def from_dict(dict_obj: Dict) -> "AgentObject":
        """Convert from dictionary."""
        ag_obj = AgentObject()
        for k, v in dict_obj.items():
            setattr(ag_obj, k, v)
        return ag_obj

    def to_dict(self):
        """Convert to dictionary."""
        result_dict = {}
        for attr, value in self.__dict__.items():
            if value is not None:
                result_dict[attr] = sanitize_json_like(value) if attr == "flowcept_settings" else value
        result_dict["type"] = "agent"
        return result_dict

    def enrich(self):
        """Enrich it."""
        if self.user is None:
            from flowcept.configs import LOGIN_NAME, FLOWCEPT_USER

            self.user = LOGIN_NAME or FLOWCEPT_USER

        if self.extra_metadata is None and EXTRA_METADATA is not None:
            _extra_metadata = (
                OmegaConf.to_container(EXTRA_METADATA) if isinstance(EXTRA_METADATA, DictConfig) else EXTRA_METADATA
            )
            self.extra_metadata = _extra_metadata

    def serialize(self):
        """Serialize it."""
        return msgpack.dumps(self.to_dict())

    @staticmethod
    def deserialize(serialized_data) -> "AgentObject":
        """Deserialize it."""
        dict_obj = msgpack.loads(serialized_data)
        obj = AgentObject()
        for k, v in dict_obj.items():
            setattr(obj, k, v)
        return obj

    def __repr__(self):
        """Set the repr."""
        return (
            f"AgentObject("
            f"agent_id={repr(self.agent_id)}, "
            f"name={repr(self.name)}, "
            f"workflow_id={repr(self.workflow_id)}, "
            f"campaign_id={repr(self.campaign_id)}, "
            f"registered_at={repr(self.registered_at)}, "
            f"user={repr(self.user)}, "
            f"extra_metadata={repr(self.extra_metadata)})"
        )

    def __str__(self):
        """Set the string."""
        return self.__repr__()
