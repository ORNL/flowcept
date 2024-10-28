"""Commons subpackage."""

from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.commons.utils import get_adapter_exception_msg
logger = FlowceptLogger()

__all__ = ['get_adapter_exception_msg']

def singleton(cls):
    """Create a singleton."""
    instances = {}

    class SingletonWrapper(cls):
        def __new__(cls, *args, **kwargs):
            if cls not in instances:
                instances[cls] = super().__new__(cls)
            return instances[cls]

    return SingletonWrapper
