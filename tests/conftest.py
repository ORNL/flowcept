"""Pytest hooks to integrate Flowcept logging with pytest's log capture."""

import logging

import pytest

from flowcept.configs import PROJECT_NAME


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    """Route Flowcept logs through pytest's logging capture and CLI output."""
    logger = logging.getLogger(PROJECT_NAME)
    logger.propagate = True
    # Remove only stream handlers so pytest's log capture/cli can show records.
    logger.handlers = [h for h in logger.handlers if not isinstance(h, logging.StreamHandler)]
    config.addinivalue_line(
        "markers",
        "safeoffline: mark tests that are safe to run with offline/no-MQ settings",
    )


@pytest.fixture
def safeoffline(request):
    """Mark a test as safe to run with offline/no-MQ settings."""
    request.node.add_marker("safeoffline")
