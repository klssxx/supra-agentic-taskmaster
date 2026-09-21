from __future__ import annotations

from pathlib import Path

from supra_agentic.state import ProjectStateManager, _get_storage_configuration


def _clear_storage_env(monkeypatch) -> None:
    for name in ("SUPRA_STORAGE_DIR", "CLOUD_RUN_PERSISTENT_DIR", "K_SERVICE"):
        monkeypatch.delenv(name, raising=False)


def test_explicit_storage_is_configured_but_not_claimed_persistent(tmp_path: Path) -> None:
    manager = ProjectStateManager(tmp_path / "explicit")
    assert manager.storage_mode == "CONFIGURED_FILESYSTEM"
    assert manager.storage_dir == tmp_path / "explicit"


def test_storage_env_is_configured_filesystem(monkeypatch, tmp_path: Path) -> None:
    _clear_storage_env(monkeypatch)
    configured = tmp_path / "mounted"
    monkeypatch.setenv("SUPRA_STORAGE_DIR", str(configured))
    path, mode = _get_storage_configuration()
    assert path == configured
    assert mode == "CONFIGURED_FILESYSTEM"


def test_cloud_run_without_mount_is_instance_ephemeral(monkeypatch) -> None:
    _clear_storage_env(monkeypatch)
    monkeypatch.setenv("K_SERVICE", "supra")
    path, mode = _get_storage_configuration()
    assert mode == "INSTANCE_EPHEMERAL"
    assert path.name == "supra-agentic"


def test_local_default_is_not_described_as_external_persistence(monkeypatch) -> None:
    _clear_storage_env(monkeypatch)
    _path, mode = _get_storage_configuration()
    assert mode == "LOCAL_FILESYSTEM"
