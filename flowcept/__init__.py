import logging

from flowcept.configs import PROJECT_NAME
from flowcept.version import __version__

from flowcept.flowcept_api.consumer_api import FlowceptConsumerAPI
from flowcept.flowcept_api.task_query_api import TaskQueryAPI

from flowcept.flowceptor.plugins.zambeze.zambeze_interceptor import (
    ZambezeInterceptor,
)
from flowcept.flowceptor.plugins.tensorboard.tensorboard_interceptor import (
    TensorboardInterceptor,
)
from flowcept.flowceptor.plugins.mlflow.mlflow_interceptor import (
    MLFlowInterceptor,
)
from flowcept.flowceptor.plugins.dask.dask_plugins import (
    FlowceptDaskSchedulerPlugin,
    FlowceptDaskWorkerPlugin,
)


def _set_logger():
    import logging

    from flowcept.configs import (
        PROJECT_NAME,
        LOG_FILE_PATH,
        LOG_STREAM_LEVEL,
        LOG_FILE_LEVEL,
    )

    # Create a custom logger
    _logger = logging.getLogger(PROJECT_NAME)
    _logger.setLevel(logging.DEBUG)
    # Create handlers
    stream_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(LOG_FILE_PATH, mode="a+")

    stream_level = getattr(logging, LOG_STREAM_LEVEL)
    stream_handler.setLevel(stream_level)
    file_level = getattr(logging, LOG_FILE_LEVEL)
    file_handler.setLevel(file_level)

    # Create formatters and add it to handlers
    c_format = logging.Formatter("[%(name)s][%(levelname)s][%(message)s]")
    f_format = logging.Formatter(
        "[%(asctime)s][%(name)s][%(levelname)s][%(message)s]"
    )
    stream_handler.setFormatter(c_format)
    file_handler.setFormatter(f_format)

    # Add handlers to the logger
    _logger.addHandler(stream_handler)
    _logger.addHandler(file_handler)

    _logger.debug(f"{PROJECT_NAME}'s base log is set up!")


# _set_logger()

# Make sure this is the last thing we call in this __init__

# from flowcept.commons.flowcept_logger import stream_handler, file_handler
# logging.getLogger(PROJECT_NAME).addHandler(stream_handler)
# logging.getLogger(PROJECT_NAME).addHandler(file_handler)
