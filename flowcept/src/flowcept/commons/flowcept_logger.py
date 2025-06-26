"""Logger module."""

import logging

from flowcept.configs import (
    PROJECT_NAME,
    LOG_FILE_PATH,
    LOG_STREAM_LEVEL,
    LOG_FILE_LEVEL,
    HOSTNAME,
)

_fmt = f"[%(name)s][%(levelname)s][{HOSTNAME}][pid=%(process)d]"
_BASE_FORMAT = _fmt + "[thread=%(thread)d][function=%(funcName)s][%(message)s]"


class FlowceptLogger(object):
    """Logger class."""

    _instance = None

    @classmethod
    def _build_logger(cls):
        # Critical + 1 will disable if user sets something not recognized
        file_level = logging._nameToLevel.get(LOG_FILE_LEVEL, logging.CRITICAL + 1)
        stream_level = logging._nameToLevel.get(LOG_STREAM_LEVEL, logging.CRITICAL + 1)

        # Create a custom logger
        logger = logging.getLogger(PROJECT_NAME)
        logger.setLevel(logging.DEBUG)

        if stream_level <= logging.CRITICAL:
            stream_handler = logging.StreamHandler()
            stream_handler.setLevel(stream_level)
            stream_format = logging.Formatter(_BASE_FORMAT)
            stream_handler.setFormatter(stream_format)
            logger.addHandler(stream_handler)

        if file_level <= logging.CRITICAL:
            file_handler = logging.FileHandler(LOG_FILE_PATH, delay=True, mode="a+")
            file_handler.setLevel(file_level)
            file_format = logging.Formatter(f"[%(asctime)s]{_BASE_FORMAT}")
            file_handler.setFormatter(file_format)
            logger.addHandler(file_handler)

        logger.debug(f"{PROJECT_NAME}'s base log is set up!")
        return logger

    def __new__(cls, *args, **kwargs) -> logging.Logger:
        """Create a new instance."""
        if not cls._instance:
            cls._instance = super(FlowceptLogger, cls).__new__(cls, *args, **kwargs)
            cls._instance._logger = FlowceptLogger._build_logger()
        return cls._instance._logger
