"""Schema management for the MCP agent context.

Owns the per-task, per-object, and per-workflow DynamicSchemaTracker instances
and all methods that update them or the corresponding DataFrames in context.
"""

from __future__ import annotations

from typing import Dict, List

import pandas as pd

from flowcept.agents.provenance_schema_manager.dynamic_schema_tracker import DynamicSchemaTracker
from flowcept.commons.flowcept_logger import FlowceptLogger


def _to_context_df(records: List[Dict]) -> pd.DataFrame:
    """Normalize a list of record dicts into a DataFrame, converting list cells to tuples."""
    _df = pd.json_normalize(records)
    for col in _df.columns:
        if _df[col].apply(lambda v: isinstance(v, list)).any():
            _df[col] = _df[col].apply(lambda v: tuple(v) if isinstance(v, list) else v)
    return pd.DataFrame(_df)


class ContextSchemaManager:
    """Manages DynamicSchemaTracker instances and DataFrame updates for the MCP agent context.

    Parameters
    ----------
    context :
        The live ``FlowceptAppContext`` whose schema/df fields are updated in place.
    tracker_config :
        Keyword args forwarded to every ``DynamicSchemaTracker`` constructor
        (e.g. ``max_examples``, ``max_str_len``).
    """

    def __init__(self, context, tracker_config: Dict):
        self.logger = FlowceptLogger()
        self._context = context
        self._tracker_config = tracker_config
        self._reset_trackers()

    def reset(self):
        """Reset all trackers to a clean state (called when agent context is reset)."""
        self._reset_trackers()

    def _reset_trackers(self):
        self.schema_tracker = DynamicSchemaTracker(**self._tracker_config)
        self.objects_schema_tracker = DynamicSchemaTracker(**self._tracker_config)
        self.workflow_schema_trackers: Dict = {}

    def update_schema_and_add_to_df(self, tasks: List[Dict]):
        """Update the task schema tracker and append normalised rows to the context DataFrame."""
        self.schema_tracker.update_with_tasks(tasks)
        self._context.tasks_schema = self.schema_tracker.get_schema()
        self._context.value_examples = self.schema_tracker.get_example_values()

        _df = _to_context_df(tasks)
        self._context.df = pd.concat([self._context.df, _df], ignore_index=True)

    def update_objects_schema_and_add_to_df(self, objects: List[Dict]):
        """Update the object schema tracker and append normalised rows to the objects DataFrame."""
        self.objects_schema_tracker.update_with_tasks(objects)
        self._context.objects_schema = self.objects_schema_tracker.get_schema()
        self._context.objects_value_examples = self.objects_schema_tracker.get_example_values()

        _df = _to_context_df(objects)
        self._context.objects_df = pd.concat([self._context.objects_df, _df], ignore_index=True)

    def update_workflow_schema_cache(self, tasks: List[Dict]):
        """Update per-workflow dynamic schema snapshots from a batch of task records."""
        by_workflow: Dict[str, List[Dict]] = {}
        for task in tasks:
            workflow_id = task.get("workflow_id")
            if workflow_id:
                by_workflow.setdefault(workflow_id, []).append(task)

        for workflow_id, workflow_tasks in by_workflow.items():
            tracker = self.workflow_schema_trackers.setdefault(
                workflow_id,
                DynamicSchemaTracker(**self._tracker_config),
            )
            tracker.update_with_tasks(workflow_tasks)
            _df = _to_context_df(workflow_tasks)
            existing = self._context.workflow_schema_cache.get(workflow_id, {}).get("current_fields", [])
            current_fields = sorted(set(existing) | set(_df.columns))
            self._context.workflow_schema_cache[workflow_id] = {
                "dynamic_schema": tracker.get_schema(),
                "value_examples": tracker.get_example_values(),
                "current_fields": current_fields,
            }

    def get_workflow_schema_snapshot(self, workflow_id: str):
        """Return the cached schema snapshot for a workflow, loading from DB on cache miss."""
        if not workflow_id:
            return None
        if workflow_id in self._context.workflow_schema_cache:
            return self._context.workflow_schema_cache[workflow_id]
        try:
            from flowcept.flowcept_api.db_api import DBAPI

            snapshot = DBAPI().get_workflow_domain_data_schema(workflow_id)
        except Exception as e:
            self.logger.exception(e)
            snapshot = None
        if snapshot:
            self._context.workflow_schema_cache[workflow_id] = snapshot
        return snapshot

    def persist_workflow_schema_snapshot(self, workflow_id: str) -> bool:
        """Persist the cached workflow schema snapshot into workflow metadata."""
        snapshot = self.get_workflow_schema_snapshot(workflow_id)
        if not snapshot:
            return False
        try:
            from flowcept.flowcept_api.db_api import DBAPI

            return DBAPI().save_workflow_domain_data_schema(workflow_id, snapshot)
        except Exception as e:
            self.logger.exception(e)
            return False
