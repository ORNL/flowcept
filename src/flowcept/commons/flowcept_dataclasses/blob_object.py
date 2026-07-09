"""Blob Object module."""

from typing import Dict, AnyStr, List


class BlobObject:
    """Blob object class.

    Represents metadata and linkage information for binary objects stored through
    ``Flowcept.db``.
    """

    object_id: AnyStr = None
    """Unique identifier for the stored blob object."""

    task_id: AnyStr = None
    """Identifier of the task associated with this blob object, if any."""

    workflow_id: AnyStr = None
    """Identifier of the workflow associated with this blob object, if any."""

    object_type: AnyStr = None
    """User-defined category label for the blob object (for example, ``ml_model``)."""

    custom_metadata: Dict = None
    """Optional user-defined metadata dictionary."""

    tags: List[str] = None
    """Optional labels associated with the object."""

    version: int = 0
    """Monotonic version of this blob object. Starts at ``0`` and increments on updates."""

    created_at: float = None
    """Epoch timestamp when the object was first persisted."""

    updated_at: float = None
    """Epoch timestamp when the object was last persisted or updated."""

    def __init__(
        self,
        object_id=None,
        task_id=None,
        workflow_id=None,
        object_type=None,
        custom_metadata=None,
        tags=None,
        version: int = 0,
        created_at: float = None,
        updated_at: float = None,
    ):
        self.object_id = object_id
        self.task_id = task_id
        self.workflow_id = workflow_id
        self.object_type = object_type
        self.custom_metadata = custom_metadata
        self.tags = tags
        self.version = 0 if version is None else int(version)
        self.created_at = created_at
        self.updated_at = updated_at

    @staticmethod
    def object_id_field():
        """Get object id field name."""
        return "object_id"

    @staticmethod
    def from_dict(dict_obj: Dict) -> "BlobObject":
        """Build a BlobObject from a dictionary."""
        obj = BlobObject()
        for k, v in dict_obj.items():
            setattr(obj, k, v)
        if getattr(obj, "version", None) is None:
            obj.version = 0
        return obj

    def to_dict(self):
        """Convert this object to a dictionary with non-null fields."""
        result_dict = {}
        for attr, value in self.__dict__.items():
            if value is not None:
                result_dict[attr] = value
        if "version" not in result_dict:
            result_dict["version"] = 0
        return result_dict

    def __repr__(self):
        """String representation."""
        return (
            f"BlobObject("
            f"object_id={repr(self.object_id)}, "
            f"task_id={repr(self.task_id)}, "
            f"workflow_id={repr(self.workflow_id)}, "
            f"object_type={repr(self.object_type)}, "
            f"custom_metadata={repr(self.custom_metadata)}, "
            f"tags={repr(self.tags)}, "
            f"version={repr(self.version)}, "
            f"created_at={repr(self.created_at)}, "
            f"updated_at={repr(self.updated_at)})"
        )

    def __str__(self):
        """String representation."""
        return self.__repr__()
