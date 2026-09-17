"""flowcept-harness: PROV-AGENT provenance capture for AI coding harnesses.

Captures what an agentic harness actually did — prompts, turns, tool calls,
subagents — as `Flowcept <https://github.com/ORNL/flowcept>`_ provenance,
modelled with PROV-AGENT (arXiv:2508.02866).

The capture path is stdlib-only and writes JSONL that Flowcept reads natively;
flowcept itself is only needed to ingest or query what was captured.

    from flowcept.agents.harness import HarnessEvent, Recorder, EventKind

    Recorder().record(HarnessEvent(
        kind=EventKind.TOOL_POST,
        harness="my_harness",
        session_id="abc123",
        tool_name="run_tests",
        tool_input={"suite": "unit"},
        tool_response={"passed": 42},
    ))
"""

from .config import Config, load_config
from .events import HarnessEvent
from .recorder import Recorder, repair_session
from .tracer import SessionTracer
from .vocab import EventKind

__all__ = [
    "Config",
    "EventKind",
    "HarnessEvent",
    "Recorder",
    "SessionTracer",
    "load_config",
    "repair_session",
]
