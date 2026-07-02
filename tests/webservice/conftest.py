"""Session-level fixtures for webservice integration tests."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from flowcept import Flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import MONGO_ENABLED


def _wait_for_df_context(min_rows: int, timeout: float = 60.0) -> bool:
    """Return True when the MCP in-memory DataFrame reaches at least min_rows rows."""
    from flowcept.agents.mcp.context_manager import ctx_manager

    deadline = time.time() + timeout
    while time.time() < deadline:
        df = ctx_manager.context.df
        if df is not None and len(df) >= min_rows:
            return True
        time.sleep(0.5)
    return False


def _wait_for_objects_in_context(min_count: int, timeout: float = 60.0) -> bool:
    """Return True when the MCP in-memory objects DataFrame reaches at least min_count rows."""
    from flowcept.agents.mcp.context_manager import ctx_manager

    deadline = time.time() + timeout
    while time.time() < deadline:
        df = ctx_manager.context.objects_df
        if df is not None and len(df) >= min_count:
            return True
        time.sleep(0.5)
    return False


def _wait_for_agents_in_context(min_count: int, timeout: float = 60.0) -> bool:
    """Return True when the MCP context holds at least min_count agent records."""
    from flowcept.agents.mcp.context_manager import ctx_manager

    deadline = time.time() + timeout
    while time.time() < deadline:
        if len(ctx_manager.context.agents) >= min_count:
            return True
        time.sleep(0.5)
    return False


def _wait_for_tasks(workflow_id: str, min_count: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or [])
        if count >= min_count:
            return True
        time.sleep(0.5)
    return False


def _wait_for_objects(workflow_id: str, min_count: int, timeout: float = 60.0) -> bool:
    from flowcept.flowcept_api.db_api import DBAPI

    deadline = time.time() + timeout
    while time.time() < deadline:
        count = len(DBAPI().blob_object_query(filter={"workflow_id": workflow_id}) or [])
        if count >= min_count:
            return True
        time.sleep(0.5)
    return False


def _wait_for_workflow(workflow_id: str, timeout: float = 60.0) -> bool:
    """Return True when a workflow document with name and FINISHED status lands in MongoDB."""
    from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

    deadline = time.time() + timeout
    while time.time() < deadline:
        docs = MongoDBDAO().workflow_query(filter={"workflow_id": workflow_id}) or []
        if docs and docs[0].get("name") and docs[0].get("status") == "FINISHED":
            return True
        time.sleep(0.5)
    return False


def _wait_for_agents(workflow_id: str, min_count: int, timeout: float = 60.0) -> bool:
    from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

    deadline = time.time() + timeout
    while time.time() < deadline:
        count = len(MongoDBDAO().agent_query(filter={"workflow_id": workflow_id}) or [])
        if count >= min_count:
            return True
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def mcp_server_instance():
    """Start a single MCP HTTP server for the entire test session.

    The server is started before any experiment fixture so the MQ consumer is
    subscribed and ready to receive live messages from the experiment.
    Skips when MQ/KVDB services are not alive.
    """
    if not Flowcept.services_alive():
        pytest.skip("Flowcept services not alive; skipping MCP server fixture.")

    from flowcept.agents.mcp.mcp_server import FlowceptMCPServer

    agent = FlowceptMCPServer().start()
    try:
        yield agent
    finally:
        agent.stop()


@pytest.fixture(scope="session")
def gridsearch_run_data(mcp_server_instance):
    """Run the Perceptron GridSearch experiment once and yield its artifacts.

    Skips automatically when:
    - MongoDB is disabled.
    - Flowcept infrastructure services (MQ/KVDB/Mongo) are not alive.
    - The LLM agent is not configured (api_key / service_provider missing).

    Yields
    ------
    dict
        Keys: ``workflow_id``, ``tasks``, ``configs``, ``results``, ``selected``,
        ``campaign_id``.
    Cleanup: deletes the campaign and all its data after the session ends.
    """
    logger = FlowceptLogger()

    if not MONGO_ENABLED:
        pytest.skip("MongoDB is disabled; gridsearch fixture requires Mongo.")
    if not Flowcept.services_alive():
        logger.warning("Skipping gridsearch session fixture: one or more services not ready (see ERROR logs above).")
        pytest.skip("One or more services not ready.")

    from tests.instrumentation_tests.ml_tests.single_layer_perceptron_test import run_gridsearch_experiment

    campaign_id = f"chat-test-gs-{uuid4()}"
    run_data = run_gridsearch_experiment(campaign_id=campaign_id)
    run_data["campaign_id"] = campaign_id

    workflow_id = run_data["workflow_id"]
    # Wait for all tasks to land in MongoDB before any chat test reads them.
    min_tasks = len(run_data.get("configs", [])) + 3  # train tasks + setup tasks
    ok = _wait_for_tasks(workflow_id, min_count=min_tasks)
    if not ok:
        count = len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or [])
        logger.warning(f"gridsearch fixture: only {count} tasks persisted after timeout.")

    # Wait for blob objects (dataset + ml_model checkpoints) — needed by DF-path object queries.
    ok = _wait_for_objects(workflow_id, min_count=2)
    if not ok:
        from flowcept.flowcept_api.db_api import DBAPI

        count = len(DBAPI().blob_object_query(filter={"workflow_id": workflow_id}) or [])
        logger.warning(f"gridsearch fixture: only {count} objects persisted after timeout.")

    # Wait for blob objects in MCP in-memory objects_df (flows MQ → context manager).
    ok = _wait_for_objects_in_context(min_count=2)
    if not ok:
        from flowcept.agents.mcp.context_manager import ctx_manager

        count = len(ctx_manager.context.objects_df) if ctx_manager.context.objects_df is not None else 0
        logger.warning(f"gridsearch fixture: MCP objects_df has only {count} rows after timeout.")

    # Wait for agents (HPCAgent + Orchestrator) — needed by list_agents tool calls.
    ok = _wait_for_agents(workflow_id, min_count=2)
    if not ok:
        from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

        count = len(MongoDBDAO().agent_query(filter={"workflow_id": workflow_id}) or [])
        logger.warning(f"gridsearch fixture: only {count} agents persisted after timeout.")

    # Wait for the workflow document itself (with name + status) to land in MongoDB.
    ok = _wait_for_workflow(workflow_id)
    if not ok:
        from flowcept.commons.daos.docdb_dao.mongodb_dao import MongoDBDAO

        wf_docs = MongoDBDAO().workflow_query(filter={"workflow_id": workflow_id}) or []
        logger.warning(f"gridsearch fixture: workflow doc state after timeout: {wf_docs}")

    # Wait for the MCP in-memory DataFrame to be populated (tasks flow from MQ → context).
    ok = _wait_for_df_context(min_rows=min_tasks)
    if not ok:
        from flowcept.agents.mcp.context_manager import ctx_manager

        df = ctx_manager.context.df
        logger.warning(f"gridsearch fixture: MCP DF has only {len(df) if df is not None else 0} rows after timeout.")

    # Wait for agent records in MCP context (agent messages flow from MQ → context.agents dict).
    ok = _wait_for_agents_in_context(min_count=2)
    if not ok:
        from flowcept.agents.mcp.context_manager import ctx_manager

        logger.warning(f"gridsearch fixture: MCP context has only {len(ctx_manager.context.agents)} agents after timeout.")

    yield run_data

    try:
        Flowcept.db.delete_campaign_data(campaign_id)
    except Exception as exc:
        logger.warning(f"gridsearch fixture cleanup failed for campaign {campaign_id}: {exc}")
