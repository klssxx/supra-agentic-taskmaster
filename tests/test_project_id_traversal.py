"""Security regression: a project id is a file key and must never escape the state dir.

Before the fix, ``project_id`` reached ``storage_dir / f"{project_id}.json"``
unvalidated, so ``"../../escaped"`` wrote a JSON file outside ``data/projects``.
These tests pin the guard at both boundaries (state manager and HTTP API) and
prove that valid ids and existing on-disk state keep working unchanged.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from supra_agentic.service import app
from supra_agentic.state import ProjectStateManager, state_manager

UNSAFE_IDS = [
    "../../escaped",
    "..\\escaped",
    "proj/../escaped",
    "a/b",
    "a\\b",
    "../",
    "..",
    ".",
    "proj.json",
    "id with space",
    "con\x00trol",
    "x" * 65,
]


def _manager(tmp_path: Path) -> tuple[ProjectStateManager, Path]:
    storage = tmp_path / "data" / "projects"
    return ProjectStateManager(storage_dir=storage), storage


@pytest.mark.parametrize("bad_id", UNSAFE_IDS)
def test_create_project_rejects_unsafe_ids(tmp_path, bad_id: str) -> None:
    manager, _storage = _manager(tmp_path)

    with pytest.raises(ValueError):
        manager.create_project(objective="probe", project_id=bad_id)

    assert list(tmp_path.rglob("*.json")) == []


def test_no_file_is_written_outside_the_state_directory(tmp_path) -> None:
    manager, _storage = _manager(tmp_path)

    for bad_id in ("../../escaped_probe", "../escaped_probe", "../../../escaped_probe"):
        with pytest.raises(ValueError):
            manager.create_project(objective="probe", project_id=bad_id)

    assert not (tmp_path / "escaped_probe.json").exists()
    assert not (tmp_path / "data" / "escaped_probe.json").exists()
    assert list(tmp_path.rglob("*.json")) == []


def test_get_project_returns_none_for_unsafe_ids(tmp_path) -> None:
    manager, _storage = _manager(tmp_path)

    assert manager.get_project("../../etc/passwd") is None
    assert manager.get_project("..") is None


def test_empty_project_id_still_generates_one(tmp_path) -> None:
    manager, _storage = _manager(tmp_path)

    posture = manager.create_project(objective="probe", project_id="")

    assert posture.project_id.startswith("proj-")


def test_project_id_length_limit(tmp_path) -> None:
    manager, storage = _manager(tmp_path)

    posture = manager.create_project(objective="ok", project_id="a" * 64)
    assert posture.project_id == "a" * 64
    assert (storage / f"{'a' * 64}.json").is_file()

    with pytest.raises(ValueError):
        manager.create_project(objective="too long", project_id="a" * 65)


def test_valid_id_round_trips_through_disk(tmp_path) -> None:
    manager, storage = _manager(tmp_path)
    manager.create_project(objective="valid objective", project_id="proj-abc_123")

    assert (storage / "proj-abc_123.json").is_file()
    reloaded = ProjectStateManager(storage_dir=storage).get_project("proj-abc_123")
    assert reloaded is not None
    assert reloaded.objective == "valid objective"


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """Aislar el singleton global sin dejar rastro entre tests."""
    projects = tmp_path / "projects"
    projects.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(state_manager, "storage_dir", projects)
    monkeypatch.setattr(state_manager, "_projects", {})
    return projects


def test_api_rejects_traversal_project_id(isolated_state) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects",
        json={"objective": "probe traversal", "project_id": "../../escaped"},
    )

    assert response.status_code == 422
    assert not (isolated_state.parent / "escaped.json").exists()
    assert list(isolated_state.parent.rglob("*.json")) == []


def test_api_accepts_a_valid_project_id(isolated_state) -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/projects",
        json={"objective": "probe valid id", "project_id": "proj-api-1"},
    )

    assert response.status_code == 201
    assert response.json()["project_id"] == "proj-api-1"
    assert (isolated_state / "proj-api-1.json").is_file()