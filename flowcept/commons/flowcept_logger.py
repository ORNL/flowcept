import logging

from flowcept.configs import (
    PROJECT_NAME,
    LOG_FILE_PATH,
    LOG_STREAM_LEVEL,
    LOG_FILE_LEVEL,
)

# Create a custom logger
logger = logging.getLogger(PROJECT_NAME)
logger.setLevel(logging.DEBUG)
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
logger.addHandler(stream_handler)
logger.addHandler(file_handler)

logger.debug(f"{PROJECT_NAME}'s base log is set up!")


def get_logger():
    return logger
