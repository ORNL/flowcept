"""Backward-compatibility re-export shim.

``ToolResult``, ``build_llm_model``, and ``normalize_message`` have moved:
  - ``ToolResult``        → ``flowcept.agents.tool_result``
  - ``build_llm_model``   → ``flowcept.agents.llm.builders``
  - ``normalize_message`` → ``flowcept.agents.llm.builders``

This module re-exports them to avoid breaking existing callers until C7 cleanup.
"""

from flowcept.agents.tool_result import ToolResult  # noqa: F401
from flowcept.agents.llm.builders import build_llm_model, normalize_message  # noqa: F401

__all__ = ["ToolResult", "build_llm_model", "normalize_message"]
