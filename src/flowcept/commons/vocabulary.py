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


class MimeType(Enum):
    """MimeTypes used in Flowcept."""

    JPEG = "image/jpeg"
    PNG = "image/png"
    GIF = "image/gif"
    BMP = "image/bmp"
    TIFF = "image/tiff"
    WEBP = "image/webp"
    SVG = "image/svg+xml"

    # Documents
    PDF = "application/pdf"

    # Data formats
    JSON = "application/json"
    CSV = "text/csv"
    JSONL = "application/x-ndjson"  # standard for JSON Lines


class ML_Types(str, Enum):
    """Common subtype values for ML workflows and tasks."""

    WORKFLOW = "ml_workflow"
    DATA_PREP = "dataprep"
    LEARNING = "learning"
    MODEL_SELECTION = "model_selection"
