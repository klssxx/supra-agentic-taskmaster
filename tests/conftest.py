"""Shared pytest fixtures for SUPRA tests.

Provides automatic test isolation for the global state_manager singleton.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from supra_agentic.state import state_manager


@pytest.fixture(autouse=True)
def isolate_state_manager(monkeypatch):
    """Isolate state_manager for each test.

    Uses monkeypatch to temporarily override:
    - state_manager.storage_dir → unique temp directory per test
    - state_manager._projects → empty dict (clears in-memory cache)

    Restores originals after test completes.
    """
    # Create unique temp directory for this test
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)

        # Save original values
        original_storage_dir = state_manager.storage_dir
        original_projects = state_manager._projects

        # Apply isolation
        monkeypatch.setattr(state_manager, "storage_dir", tmp_path)
        monkeypatch.setattr(state_manager, "_projects", {})

        yield

        # monkeypatch automatically restores after yield
        # No manual cleanup needed


# Optional: fixture for tests that need the original state_manager
# (without isolation) - use explicitly when needed
@pytest.fixture
def real_state_manager():
    """Provide access to the real (unisolated) state_manager.

    Use sparingly - only for tests that specifically need to test
    cross-test persistence or global behavior.
    """
    return state_manager