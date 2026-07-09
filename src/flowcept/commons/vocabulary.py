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


class PROV_AGENT(str, Enum):
    """Activity subtype vocabulary for agentic AI workflows (PROV-AGENT model).

    PROV-AGENT is a W3C PROV extension for capturing provenance of agentic AI
    workflows (arXiv:2508.02866).  Each value here names a distinct
    ``prov:Activity`` class in that model.  Flowcept records these as the
    ``subtype`` field on :class:`~flowcept.commons.flowcept_dataclasses.task_object.TaskObject`,
    enabling the UI and query layer to filter and visualise AI-agent activities
    separately from regular workflow tasks.

    W3C PROV mapping
    ----------------
    All values represent ``prov:Activity`` instances.  The associated entities
    and relations are:

    - **AIModelInvocation** *used* ``Prompt`` (entity) and *used* ``AIModel`` (entity).
      ``ResponseData`` (entity) *wasGeneratedBy* the invocation.
      The invocation *wasAssociatedWith* the ``AIAgent``.

    - **AgentTool** *used* tool input arguments (``DomainData``).
      Return values *wasGeneratedBy* the tool call.
      The tool *wasAssociatedWith* the ``AIAgent``.
      An ``AIModelInvocation`` that the tool triggers *wasInformedBy* the tool
      call — this ``wasInformedBy`` edge is the key link for root-cause analysis
      and downstream impact tracing.

    Usage
    -----
    >>> from flowcept.commons.vocabulary import PROV_AGENT
    >>> task_obj.subtype = PROV_AGENT.AI_MODEL_INVOCATION
    >>> task_obj.subtype = PROV_AGENT.AGENT_TOOL
    """

    AI_MODEL_INVOCATION = "ai_model_invocation"
    """A single LLM prompt→response call (``AIModelInvocation`` in PROV-AGENT).

    Captured automatically by :class:`~flowcept.instrumentation.flowcept_agent_task.FlowceptLLM`
    for every ``.invoke()`` call.  Recorded fields: ``used.prompt``,
    ``generated.response``, ``custom_metadata.llm_usage``,
    ``custom_metadata.response_metadata``.
    """

    AGENT_TOOL = "agent_tool"
    """A tool execution by an AI agent (``AgentTool`` in PROV-AGENT).

    Captured automatically by the
    :func:`~flowcept.instrumentation.flowcept_agent_task.agent_flowcept_task`
    decorator (applied to MCP tools and LangGraph tool nodes).  Recorded
    fields: ``used`` = tool input arguments, ``generated`` = tool return value.
    """
