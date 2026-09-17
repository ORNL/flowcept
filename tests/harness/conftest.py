"""Shared fixtures.

Every test gets its own capture home so that state files and buffers from one
test can never be seen by another.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from flowcept.agents.harness.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(home=tmp_path / "home", debug=True)


@pytest.fixture
def buffer_records(config: Config):
    """Return a reader for every record written to any buffer."""

    def read() -> list[dict]:
        records: list[dict] = []
        for path in sorted(config.buffers_dir.glob("*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    records.append(json.loads(line))
        return records

    return read
