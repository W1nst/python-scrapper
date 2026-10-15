"""Shared pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from tourvisor_mcp.client import TourvisorClient  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> TourvisorClient:
    """A client whose disk cache lives in a temporary directory."""
    return TourvisorClient(cache_dir=tmp_path / ".cache", poll_interval=0.5, poll_timeout=60)
