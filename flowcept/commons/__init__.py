from flowcept.commons.utils import get_adapter_exception_msg
from flowcept.commons.flowcept_logger import FlowceptLogger

logger = FlowceptLogger()


def singleton(cls):
    instances = {}

    class SingletonWrapper(cls):
        def __new__(cls, *args, **kwargs):
            if cls not in instances:
                instances[cls] = super().__new__(cls)
            return instances[cls]

    return SingletonWrapper
