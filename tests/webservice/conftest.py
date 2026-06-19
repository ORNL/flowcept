"""Session-level fixtures for webservice integration tests."""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from flowcept import Flowcept
from flowcept.commons.flowcept_logger import FlowceptLogger
from flowcept.configs import MONGO_ENABLED


def _wait_for_tasks(workflow_id: str, min_count: int, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        count = len(Flowcept.db.task_query(filter={"workflow_id": workflow_id}) or [])
        if count >= min_count:
            return True
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def gridsearch_run_data():
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

    yield run_data

    try:
        Flowcept.db.delete_campaign_data(campaign_id)
    except Exception as exc:
        logger.warning(f"gridsearch fixture cleanup failed for campaign {campaign_id}: {exc}")
