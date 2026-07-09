"""Abstract base class enforcing symmetry between DB and DF query paths."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from flowcept.agents.tool_result import ToolResult


class BaseQueryTools(ABC):
    """Common interface for DB-backed (DBQueryTools) and in-memory-DF (DFQueryTools) query paths.

    Subclasses implement path-specific logic.  The two concrete shared methods
    (``list_agents``, ``list_campaigns``) always delegate to the DB layer since
    agent and campaign derivations are DB-only operations.
    """

    @abstractmethod
    def query_tasks(self, structured_arg: Any) -> ToolResult:
        """Query tasks.

        Parameters
        ----------
        structured_arg :
            DB path: Mongo-style filter dict.  DF path: pandas code string.
        """

    @abstractmethod
    def query_objects(self, structured_arg: Any) -> ToolResult:
        """Query objects (blobs, models, datasets).

        Parameters
        ----------
        structured_arg :
            DB path: Mongo-style filter dict.  DF path: pandas code string.
        """

    @abstractmethod
    def query_workflows(self, structured_arg: Any = None) -> ToolResult:
        """Query workflows.

        Parameters
        ----------
        structured_arg :
            DB path: Mongo-style filter dict.  DF path: ignored (returns in-memory context).
        """

    @abstractmethod
    def generate_plot(self, structured_arg: Any) -> ToolResult:
        """Generate a plot.

        Parameters
        ----------
        structured_arg :
            DB path: declarative chart card_spec dict.
            DF path: dict with ``result_code`` and ``plot_code`` strings.
        """

    @abstractmethod
    def get_schema_context(self) -> str:
        """Return a schema context string for injection into the LLM system prompt."""

    @abstractmethod
    def build_query_prompt(self, query: str, schema: str = None) -> str:
        """Build a full prompt for external LLM query/code generation.

        Used only by non-LangGraph orchestrators that fetch prompts via MCP
        and drive their own LLM.  The LangGraph chat path injects schema
        context into the system prompt instead of calling this.
        """

    @staticmethod
    def enrich_context(context: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Enrich chat context with schema for the DB or DF path.

        Both paths receive the workflow-level schema (field names and example
        values for the active workflow).  The DF path additionally receives the
        in-memory DataFrame schema so the LLM can write correct pandas code.

        Parameters
        ----------
        context : dict, optional
            Chat context dict (workflow_id, campaign_id, tool_context, …).

        Returns
        -------
        dict or None
            Enriched context with ``schema_context`` added.
        """
        if not context:
            return context
        from flowcept.agents.mcp.mcp_client import run_tool

        enriched = dict(context)
        tool_context = enriched.get("tool_context", "db")

        try:
            payload = json.loads(
                run_tool(
                    "get_schema_context",
                    kwargs={"tool_context": tool_context, "workflow_id": enriched.get("workflow_id")},
                )[0]
            )
            if payload.get("code", 500) < 400 and isinstance(payload.get("result"), dict):
                enriched["schema_context"] = payload["result"].get("prompt_context")
        except Exception:
            pass

        return enriched

    def list_agents(self, filter: Optional[Dict] = None) -> ToolResult:
        """List agents — shared DB query, identical for both paths."""
        from flowcept.agents.data_query_tools.db_query_tools import list_agents as _list_agents

        return _list_agents(filter=filter)

    def list_campaigns(self, campaign_id: Optional[str] = None) -> ToolResult:
        """List campaigns — shared DB query, identical for both paths."""
        from flowcept.agents.data_query_tools.db_query_tools import list_campaigns as _list_campaigns

        return _list_campaigns(campaign_id=campaign_id)
