"""Vocab module."""

from enum import Enum


class Vocabulary:
    """Vocab class."""

    class Settings:
        """Setting class."""

        ADAPTERS = "adapters"
        KIND = "kind"

        ZAMBEZE_KIND = "zambeze"
        MLFLOW_KIND = "mlflow"
        TENSORBOARD_KIND = "tensorboard"
        DASK_KIND = "dask"


class Status(str, Enum):
    """Status class.

    Inheriting from str here for JSON serialization.
    """

    SUBMITTED = "SUBMITTED"
    WAITING = "WAITING"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    ERROR = "ERROR"
    UNKNOWN = "UNKNOWN"

    @staticmethod
    def get_finished_statuses():
        """Get finished status."""
        return [Status.FINISHED, Status.ERROR]
