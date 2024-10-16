"""Logger module."""

import logging

from flowcept.configs import (
    PROJECT_NAME,
    LOG_FILE_PATH,
    LOG_STREAM_LEVEL,
    LOG_FILE_LEVEL,
    HOSTNAME,
)


class FlowceptLogger(object):
    """Logger class."""

    _instance = None

    @classmethod
    def _build_logger(cls):
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
        fmt = f"[%(name)s][%(levelname)s][{HOSTNAME}][pid=%(process)d]"
        base_format = fmt + "[thread=%(thread)d][function=%(funcName)s][%(message)s]"
        stream_format = logging.Formatter(base_format)
        file_format = logging.Formatter(f"[%(asctime)s]{base_format}")
        stream_handler.setFormatter(stream_format)
        file_handler.setFormatter(file_format)

        # Add handlers to the logger
        logger.addHandler(stream_handler)
        logger.addHandler(file_handler)

        logger.debug(f"{PROJECT_NAME}'s base log is set up!")

        return logger

    def __new__(cls, *args, **kwargs) -> logging.Logger:
        """Create a new instance."""
        if not cls._instance:
            cls._instance = super(FlowceptLogger, cls).__new__(cls, *args, **kwargs)
            cls._instance._logger = FlowceptLogger._build_logger()
        return cls._instance._logger
