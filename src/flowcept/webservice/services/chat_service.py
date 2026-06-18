"""Backward-compatibility re-export shim.

``run_chat`` has moved to ``flowcept.agents.chat_orchestration.chat_orchestrator_service``.
This module re-exports it to avoid breaking existing callers.
"""

from flowcept.agents.chat_orchestration.chat_orchestrator_service import run_chat  # noqa: F401

__all__ = ["run_chat"]
