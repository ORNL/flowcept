"""Commons subpackage."""

from flowcept.commons.flowcept_logger import FlowceptLogger

logger = FlowceptLogger()


def singleton(cls):
    """Create a singleton."""
    instances = {}

    class SingletonWrapper(cls):
        def __new__(cls, *args, **kwargs):
            if cls not in instances:
                instances[cls] = super().__new__(cls)
            return instances[cls]

    return SingletonWrapper
