"""Shared fixtures for the SUPRA test suite.

SUP-14: the suite used to mutate the global ``state_manager`` singleton
(``storage_dir`` and the in-memory ``_projects`` cache) without restoring it,
which made test results order-dependent and left the process with a dangling
tmp path after the run.  Every test now gets an isolated state directory.
"""

from __future__ import annotations

import pytest

from supra_agentic.state import state_manager


@pytest.fixture(autouse=True)
def isolated_state(tmp_path, monkeypatch):
    """Point the global state manager at a per-test directory.

    ``tmp_path`` is per-test and pytest cleans it up afterwards, so no test
    can see projects written by another test, and the previous test's
    directory is not left dangling in the global.
    """
    monkeypatch.setattr(state_manager, "storage_dir", tmp_path / "projects")
    monkeypatch.setattr(state_manager, "_projects", {})
    yield
