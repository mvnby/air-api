from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.ha import pitr_operation_cleanup as cleanup


OPERATION_ID = "a" * 32
ACTIVE_ID = "b" * 32


@pytest.fixture
def isolated_cleanup(tmp_path, monkeypatch):
    roots = [tmp_path / "physical", tmp_path / "logical", tmp_path / "basebackup"]
    for root in roots:
        root.mkdir(mode=0o700)
    monkeypatch.setattr(cleanup, "PHYSICAL_ROOT", roots[0])
    monkeypatch.setattr(cleanup, "LOGICAL_ROOT", roots[1])
    monkeypatch.setattr(cleanup, "BASEBACKUP_ROOT", roots[2])
    monkeypatch.setattr(cleanup, "RECONCILE_LOCK", tmp_path / "cleanup.lock")
    monkeypatch.setattr(cleanup, "ROOT_UID", os.geteuid())
    monkeypatch.setattr(cleanup, "ROOT_GID", os.getegid())
    monkeypatch.setattr(cleanup, "POSTGRES_UID", os.geteuid())
    monkeypatch.setattr(cleanup, "POSTGRES_GID", os.getegid())
    monkeypatch.setattr(cleanup, "_validate_containers", lambda _operation_id: ([], []))
    monkeypatch.setattr(cleanup, "_validate_volumes", lambda _operation_id: ([], []))
    monkeypatch.setattr(cleanup, "_remove_containers", lambda _items, _query: None)
    monkeypatch.setattr(cleanup, "_remove_volumes", lambda _items, _query: None)
    return roots


def _operation(root: Path, operation_id: str = OPERATION_ID) -> Path:
    path = root / operation_id
    path.mkdir(mode=0o700)
    return path


def _file(path: Path, payload: bytes = b"artifact") -> None:
    path.write_bytes(payload)
    path.chmod(0o600)


def test_cleans_physical_logical_and_basebackup_operation_trees(isolated_cleanup):
    physical_root, logical_root, basebackup_root = isolated_cleanup
    physical = _operation(physical_root)
    _file(physical / "prepare.log")
    _file(physical / "pg_verifybackup.log")
    restore = physical / "restore"
    restore.mkdir(mode=0o700)
    data = restore / "data"
    data.mkdir(mode=0o700)
    _file(data / "PG_VERSION", b"15\n")
    logical = _operation(logical_root)
    for name in ("latest.sql", "restore.normalized.sql", "container.env"):
        _file(logical / name)
    basebackup = _operation(basebackup_root)
    for name in ("base.tar.gz", "pg_wal.tar.gz", "backup_manifest", "metadata.json"):
        _file(basebackup / name)

    cleanup.cleanup_operation_artifacts(OPERATION_ID)

    assert not physical.exists()
    assert not logical.exists()
    assert not basebackup.exists()


def test_rejects_unknown_or_linked_state_without_partial_deletion(isolated_cleanup):
    physical_root, logical_root, _ = isolated_cleanup
    physical = _operation(physical_root)
    _file(physical / "prepare.log")
    _file(physical / "unknown")
    logical = _operation(logical_root)
    target = logical / "latest.sql"
    _file(target)
    (logical / "restore.log").symlink_to(target)

    with pytest.raises(RuntimeError, match="unknown entry"):
        cleanup.cleanup_operation_artifacts(OPERATION_ID)

    assert (physical / "prepare.log").exists()
    assert (physical / "unknown").exists()
    assert logical.exists()


def test_unknown_logical_artifact_does_not_partially_delete_valid_physical_state(
    isolated_cleanup,
):
    physical_root, logical_root, _ = isolated_cleanup
    physical = _operation(physical_root)
    _file(physical / "prepare.log")
    logical = _operation(logical_root)
    _file(logical / "unexpected.sql")

    with pytest.raises(RuntimeError, match="unknown entry"):
        cleanup.cleanup_operation_artifacts(OPERATION_ID)

    assert (physical / "prepare.log").exists()
    assert (logical / "unexpected.sql").exists()


def test_invalid_state_is_rejected_before_any_runtime_asset_is_removed(
    isolated_cleanup,
    monkeypatch,
):
    _, logical_root, _ = isolated_cleanup
    logical = _operation(logical_root)
    _file(logical / "unexpected.sql")
    removed: list[str] = []
    monkeypatch.setattr(
        cleanup,
        "_validate_containers",
        lambda _operation_id: (["f" * 64], ["container-query"]),
    )
    monkeypatch.setattr(
        cleanup,
        "_remove_containers",
        lambda _items, _query: removed.append("container"),
    )

    with pytest.raises(RuntimeError, match="unknown entry"):
        cleanup.cleanup_operation_artifacts(OPERATION_ID)

    assert removed == []


def test_reconcile_removes_only_stale_operation_directories(isolated_cleanup):
    physical_root, logical_root, _ = isolated_cleanup
    stale = _operation(physical_root)
    _file(stale / "prepare.log")
    active = _operation(logical_root, ACTIVE_ID)
    _file(active / "restore.log")

    removed = cleanup.reconcile_orphan_artifacts({ACTIVE_ID})

    assert removed == [OPERATION_ID]
    assert not stale.exists()
    assert active.exists()


def test_reconcile_fails_closed_on_unbound_legacy_directory(isolated_cleanup):
    physical_root, _, _ = isolated_cleanup
    (physical_root / "20260714T120000Z-123").mkdir(mode=0o700)

    with pytest.raises(RuntimeError, match="unbound entry"):
        cleanup.reconcile_orphan_artifacts(set())
