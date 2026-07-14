#!/usr/bin/env python3
"""Strict cleanup of runtime and host artifacts owned by one PITR operation."""

from __future__ import annotations

import fcntl
import json
import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Iterable, Sequence


ROOT_UID = 0
ROOT_GID = 0
POSTGRES_UID = 70
POSTGRES_GID = 70
OPERATION_RE = re.compile(r"^[0-9a-f]{32}$")
CONTAINER_ID_RE = re.compile(r"^[0-9a-f]{12,64}$")
BASEBACKUP_FILE_RE = re.compile(
    r"^(?:base\.tar\.gz|pg_wal\.tar\.gz|backup_manifest|metadata\.json|[1-9][0-9]*\.tar\.gz)$"
)
PHYSICAL_ROOT = Path("/var/lib/mvn-postgres-pitr/restore-drills")
LOGICAL_ROOT = Path("/var/lib/mvn-postgres-pitr/logical-restore-drills")
BASEBACKUP_ROOT = Path("/var/lib/mvn-postgres-pitr/basebackups")
RECONCILE_LOCK = Path("/run/lock/mvn-postgres-pitr-cleanup.lock")
MAX_TREE_ENTRIES = 300_000
MAX_TREE_DEPTH = 64
LOGICAL_FILES = frozenset(
    {
        "latest.sql",
        "latest.sql.gz",
        "restore.sql",
        "restore.normalized.sql",
        "restore.log",
        "container.env",
    }
)
CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}


def _container_contracts(operation_id: str) -> dict[str, dict[str, str]]:
    """Return every reviewed container name that one operation may own."""
    return {
        f"mvn-logical-restore-download-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.purpose": "api-restore-drill",
        },
        f"mvn-logical-restore-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.purpose": "api-restore-drill",
        },
        f"mvn-pitr-pg-basebackup-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "basebackup",
        },
        f"mvn-pitr-basebackup-upload-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "basebackup-upload",
        },
        f"mvn-pitr-credential-probe-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "credential-probe",
        },
        f"mvn-pitr-remote-status-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "remote-status",
        },
        f"mvn-pitr-restore-prepare-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "restore-prepare",
        },
        f"mvn-pitr-restore-drill-{operation_id}-verify": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "restore-verify",
        },
        f"mvn-pitr-restore-drill-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "restore-drill",
        },
        f"mvn-pitr-wal-upload-{operation_id}": {
            "com.mvn.pitr.operation": operation_id,
            "com.mvn.pitr.phase": "wal-upload",
        },
    }


def _run(args: Sequence[str], *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        env=CLEAN_ENV,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _open_cleanup_lock() -> int:
    descriptor = os.open(
        RECONCILE_LOCK,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise RuntimeError("PITR cleanup lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX)
    return descriptor


def _validate_containers(operation_id: str) -> tuple[list[str], list[str]]:
    query = [
        "docker",
        "ps",
        "-aq",
        "--filter",
        f"label=com.mvn.pitr.operation={operation_id}",
    ]
    result = _run(query)
    if result.returncode != 0:
        raise RuntimeError("could not enumerate PITR operation containers")
    identifiers = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if (
        len(identifiers) > len(_container_contracts(operation_id))
        or len(set(identifiers)) != len(identifiers)
        or any(not CONTAINER_ID_RE.fullmatch(item) for item in identifiers)
    ):
        raise RuntimeError("PITR operation container set is invalid")
    contracts = _container_contracts(operation_id)
    verified: list[str] = []
    seen_names: set[str] = set()
    for identifier in identifiers:
        named = _run(["docker", "inspect", "--format", "{{json .Name}}", identifier])
        inspected = _run(
            ["docker", "inspect", "--format", "{{json .Config.Labels}}", identifier]
        )
        if named.returncode != 0 or inspected.returncode != 0:
            continue
        try:
            raw_name = json.loads(named.stdout)
            labels = json.loads(inspected.stdout)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("PITR operation container identity is invalid") from exc
        name = raw_name.removeprefix("/") if isinstance(raw_name, str) else ""
        required_labels = contracts.get(name)
        if (
            not name
            or name in seen_names
            or required_labels is None
            or not isinstance(labels, dict)
            or any(labels.get(key) != value for key, value in required_labels.items())
        ):
            raise RuntimeError("PITR operation container set is invalid")
        seen_names.add(name)
        verified.append(identifier)
    return verified, query


def _remove_containers(identifiers: Sequence[str], query: Sequence[str]) -> None:
    for identifier in identifiers:
        if _run(["docker", "rm", "-f", identifier], timeout=60).returncode != 0:
            if _run(["docker", "inspect", identifier]).returncode == 0:
                raise RuntimeError("could not remove PITR operation container")
    verify = _run(query)
    if verify.returncode != 0 or verify.stdout.strip():
        raise RuntimeError("PITR operation containers remained after cleanup")


def _cleanup_containers(operation_id: str) -> None:
    identifiers, query = _validate_containers(operation_id)
    _remove_containers(identifiers, query)


def _validate_volumes(operation_id: str) -> tuple[list[str], list[str]]:
    query = [
        "docker",
        "volume",
        "ls",
        "-q",
        "--filter",
        f"label=com.mvn.pitr.operation={operation_id}",
    ]
    result = _run(query)
    if result.returncode != 0:
        raise RuntimeError("could not enumerate PITR operation volumes")
    names = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    expected = f"mvn-logical-restore-{operation_id}-data"
    if len(names) > 1 or any(name != expected for name in names):
        raise RuntimeError("PITR operation volume set is invalid")
    verified: list[str] = []
    for name in names:
        inspected = _run(
            ["docker", "volume", "inspect", "--format", "{{json .Labels}}", name]
        )
        if inspected.returncode != 0:
            continue
        try:
            labels = json.loads(inspected.stdout)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("PITR operation volume labels are invalid") from exc
        if not isinstance(labels, dict) or (
            labels.get("com.mvn.pitr.operation") != operation_id
            or labels.get("com.mvn.purpose") != "api-restore-drill"
        ):
            raise RuntimeError("refusing to remove an unrelated volume")
        verified.append(name)
    return verified, query


def _remove_volumes(names: Sequence[str], query: Sequence[str]) -> None:
    for name in names:
        if _run(["docker", "volume", "rm", name], timeout=60).returncode != 0:
            if _run(["docker", "volume", "inspect", name]).returncode == 0:
                raise RuntimeError("could not remove PITR operation volume")
    verify = _run(query)
    if verify.returncode != 0 or verify.stdout.strip():
        raise RuntimeError("PITR operation volumes remained after cleanup")


def _cleanup_volumes(operation_id: str) -> None:
    names, query = _validate_volumes(operation_id)
    _remove_volumes(names, query)


def _validate_state_root(root: Path) -> bool:
    try:
        metadata = root.lstat()
    except FileNotFoundError:
        return False
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError(f"PITR cleanup state root is unsafe: {root}")
    return True


def _validate_operation_dir(root: Path, operation_id: str) -> Path | None:
    if not _validate_state_root(root):
        return None
    path = root / operation_id
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return None
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or metadata.st_nlink < 2
    ):
        raise RuntimeError(f"PITR operation state directory is unsafe: {path}")
    return path


def _validate_regular(path: Path, *, owners: set[tuple[int, int]], exact_mode: int | None) -> None:
    metadata = path.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or (metadata.st_uid, metadata.st_gid) not in owners
        or metadata.st_nlink != 1
        or (exact_mode is not None and stat.S_IMODE(metadata.st_mode) != exact_mode)
        or (exact_mode is None and metadata.st_mode & 0o022)
    ):
        raise RuntimeError(f"PITR operation state file is unsafe: {path}")


def _validate_flat(
    path: Path,
    *,
    allowed: frozenset[str],
    pattern: re.Pattern[str] | None,
) -> list[Path]:
    entries = list(path.iterdir())
    if len(entries) > 128:
        raise RuntimeError(f"PITR operation state has too many entries: {path}")
    for entry in entries:
        if entry.name not in allowed and (pattern is None or not pattern.fullmatch(entry.name)):
            raise RuntimeError(f"PITR operation state contains an unknown entry: {entry}")
        _validate_regular(entry, owners={(ROOT_UID, ROOT_GID)}, exact_mode=0o600)
    return entries


def _validated_tree(root: Path) -> tuple[list[Path], list[Path]]:
    files: list[Path] = []
    directories: list[Path] = [root]
    owners = {(ROOT_UID, ROOT_GID), (POSTGRES_UID, POSTGRES_GID)}
    root_metadata = root.lstat()
    if (
        stat.S_ISLNK(root_metadata.st_mode)
        or not stat.S_ISDIR(root_metadata.st_mode)
        or (root_metadata.st_uid, root_metadata.st_gid) not in owners
        or root_metadata.st_mode & 0o022
        or root_metadata.st_nlink < 2
    ):
        raise RuntimeError(f"PITR physical restore directory is unsafe: {root}")
    for current, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        if len(current_path.relative_to(root).parts) > MAX_TREE_DEPTH:
            raise RuntimeError("PITR physical restore tree is too deep")
        for name in directory_names:
            path = current_path / name
            metadata = path.lstat()
            if (
                stat.S_ISLNK(metadata.st_mode)
                or not stat.S_ISDIR(metadata.st_mode)
                or (metadata.st_uid, metadata.st_gid) not in owners
                or metadata.st_mode & 0o022
                or metadata.st_nlink < 2
            ):
                raise RuntimeError(f"PITR physical restore directory is unsafe: {path}")
            directories.append(path)
        for name in file_names:
            path = current_path / name
            _validate_regular(path, owners=owners, exact_mode=None)
            files.append(path)
        if len(files) + len(directories) > MAX_TREE_ENTRIES:
            raise RuntimeError("PITR physical restore tree has too many entries")
    return files, directories


def _validate_physical(path: Path) -> tuple[list[Path], list[Path], list[Path]]:
    allowed = {"prepare.log", "pg_verifybackup.log", "restore"}
    entries = list(path.iterdir())
    if any(entry.name not in allowed for entry in entries):
        raise RuntimeError("PITR physical restore state contains an unknown entry")
    logs = [entry for entry in entries if entry.name != "restore"]
    for log in logs:
        _validate_regular(log, owners={(ROOT_UID, ROOT_GID)}, exact_mode=0o600)
    restore = path / "restore"
    files: list[Path] = []
    directories: list[Path] = []
    if any(entry.name == "restore" for entry in entries):
        files, directories = _validated_tree(restore)
    return files, directories, logs


def _validate_state(operation_id: str) -> tuple[object, ...]:
    physical = _validate_operation_dir(PHYSICAL_ROOT, operation_id)
    logical = _validate_operation_dir(LOGICAL_ROOT, operation_id)
    basebackup = _validate_operation_dir(BASEBACKUP_ROOT, operation_id)
    physical_plan = _validate_physical(physical) if physical is not None else None
    logical_files = (
        _validate_flat(logical, allowed=LOGICAL_FILES, pattern=None)
        if logical is not None
        else []
    )
    basebackup_files = (
        _validate_flat(basebackup, allowed=frozenset(), pattern=BASEBACKUP_FILE_RE)
        if basebackup is not None
        else []
    )

    return physical, physical_plan, logical, logical_files, basebackup, basebackup_files


def _remove_state(plan: tuple[object, ...]) -> None:
    physical, physical_plan, logical, logical_files, basebackup, basebackup_files = plan
    if physical is not None and physical_plan is not None:
        files, directories, logs = physical_plan
        for item in files:
            item.unlink()
        for item in sorted(directories, key=lambda value: len(value.parts), reverse=True):
            item.rmdir()
        for log in logs:
            log.unlink()
        physical.rmdir()
    if logical is not None:
        for item in logical_files:
            item.unlink()
        logical.rmdir()
    if basebackup is not None:
        for item in basebackup_files:
            item.unlink()
        basebackup.rmdir()


def _cleanup_state(operation_id: str) -> None:
    _remove_state(_validate_state(operation_id))


def _cleanup_unlocked(operation_id: str) -> None:
    containers, container_query = _validate_containers(operation_id)
    volumes, volume_query = _validate_volumes(operation_id)
    state = _validate_state(operation_id)
    # Prove the complete, exact operation asset set before deleting any part
    # of it.  A foreign path or mislabeled runtime object leaves the operation
    # intact for operator inspection.
    _remove_containers(containers, container_query)
    _remove_volumes(volumes, volume_query)
    _remove_state(state)


def cleanup_operation_artifacts(operation_id: str) -> None:
    if not OPERATION_RE.fullmatch(operation_id):
        raise RuntimeError("PITR cleanup operation ID is invalid")
    descriptor = _open_cleanup_lock()
    try:
        _cleanup_unlocked(operation_id)
    finally:
        os.close(descriptor)


def _operation_directories(root: Path) -> Iterable[str]:
    if not _validate_state_root(root):
        return ()
    names: list[str] = []
    for entry in root.iterdir():
        if not OPERATION_RE.fullmatch(entry.name):
            raise RuntimeError(f"PITR state root contains an unbound entry: {entry}")
        _validate_operation_dir(root, entry.name)
        names.append(entry.name)
        if len(names) > 64:
            raise RuntimeError("PITR state root has too many operation directories")
    return names


def reconcile_orphan_artifacts(active_operation_ids: set[str]) -> list[str]:
    if any(not OPERATION_RE.fullmatch(item) for item in active_operation_ids):
        raise RuntimeError("active PITR operation ID set is invalid")
    descriptor = _open_cleanup_lock()
    try:
        discovered = set()
        for root in (PHYSICAL_ROOT, LOGICAL_ROOT, BASEBACKUP_ROOT):
            discovered.update(_operation_directories(root))
        stale = sorted(discovered - active_operation_ids)
        for operation_id in stale:
            _cleanup_unlocked(operation_id)
        return stale
    finally:
        os.close(descriptor)
