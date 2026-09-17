"""Vocabulary used when mapping harness activity onto PROV-AGENT.

PROV-AGENT (arXiv:2508.02866) is the W3C PROV extension Flowcept uses for
agentic workflows. It defines two activity classes that map cleanly onto what a
coding harness does, and Flowcept's UI and query layer already understand them:

``ai_model_invocation``
    One prompt -> one response. We record this at *turn* granularity for
    hook-based harnesses (a hook cannot see individual API calls) and at
    *call* granularity for SDK and OpenTelemetry adapters, which can.
    ``custom_metadata.granularity`` says which.

``agent_tool``
    One tool execution by the agent — a ``Bash`` run, an ``Edit``, an MCP tool.

Everything else a harness emits (compaction, notifications, permission
decisions) is lifecycle context rather than a PROV activity class, so it is
recorded with the ``harness_event`` subtype and kept out of the two classes
above so dataflow queries stay clean.
"""

from __future__ import annotations

# --- PROV-AGENT activity subtypes (must match flowcept.commons.vocabulary) ---
AI_MODEL_INVOCATION = "ai_model_invocation"
AGENT_TOOL = "agent_tool"

# --- flowcept-harness extensions --------------------------------------------
HARNESS_EVENT = "harness_event"
"""Lifecycle event with no dataflow of its own (compaction, notification)."""

AGENT_SESSION = "agent_session"
"""Workflow subtype for one interactive harness session."""

SUBAGENT_SESSION = "subagent_session"
"""Workflow subtype for a subagent nested under a session."""

# --- Statuses (must match flowcept.commons.vocabulary.Status) ---------------
STATUS_RUNNING = "RUNNING"
STATUS_FINISHED = "FINISHED"
STATUS_ERROR = "ERROR"
STATUS_UNKNOWN = "UNKNOWN"

# --- Record types (the "type" discriminator Flowcept's inserter reads) ------
TYPE_TASK = "task"
TYPE_WORKFLOW = "workflow"
TYPE_AGENT = "agent"

ADAPTER_ID = "flowcept.agents.harness"


#: Normalized event kinds the recorder understands. Adapters translate their
#: harness's native event names into these.
class EventKind:
    """Harness-independent lifecycle events."""

    SESSION_START = "session_start"
    SESSION_END = "session_end"
    PROMPT = "prompt"
    TURN_END = "turn_end"
    TOOL_PRE = "tool_pre"
    TOOL_POST = "tool_post"
    TOOL_ERROR = "tool_error"
    LLM_CALL = "llm_call"
    SUBAGENT_START = "subagent_start"
    SUBAGENT_STOP = "subagent_stop"
    NOTIFICATION = "notification"
    COMPACT = "compact"

    ALL = (
        SESSION_START,
        SESSION_END,
        PROMPT,
        TURN_END,
        TOOL_PRE,
        TOOL_POST,
        TOOL_ERROR,
        LLM_CALL,
        SUBAGENT_START,
        SUBAGENT_STOP,
        NOTIFICATION,
        COMPACT,
    )
