#!/usr/bin/env python3
"""Run one scheduled PITR job under the shared hardened host lock."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Sequence

try:
    from scripts.ha.pitr_operation_guard import (
        reconcile_project_operations,
        run_guarded_process,
    )
except ModuleNotFoundError:  # Installed host execution.
    guard_path = Path("/usr/local/sbin/mvn_postgres_pitr_operation_guard.py")
    specification = importlib.util.spec_from_file_location(
        "mvn_postgres_pitr_operation_guard", guard_path
    )
    if specification is None or specification.loader is None:
        raise
    guard_module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = guard_module
    specification.loader.exec_module(guard_module)
    reconcile_project_operations = guard_module.reconcile_project_operations
    run_guarded_process = guard_module.run_guarded_process


LOCK_PATH = Path("/run/lock/mvn-postgres-pitr-prerequisites.lock")
MAINTENANCE_MARKER = Path("/run/mvn-postgres-pitr-maintenance")
RELEASE_MANIFEST = Path("/var/lib/mvn-postgres-pitr/release-manifest.json")
ALLOWED_TARGETS = {
    "/opt/air-api": "docker-compose.patroni.yml",
    "/opt/mvn-reserve": "docker-compose.patroni.yml",
}
PHASE_HELPERS = {
    "wal-upload": Path("/usr/local/sbin/mvn-postgres-pitr-upload-wal"),
    "basebackup": Path("/usr/local/sbin/mvn-postgres-pitr-basebackup"),
}
COMMON_HELPERS = (
    Path("/usr/local/sbin/mvn-postgres-pitr-runtime-check"),
    Path("/usr/local/sbin/mvn-postgres-pitr-upload"),
    Path("/usr/local/sbin/mvn-postgres-pitr-immutable-upload"),
    Path("/usr/local/sbin/mvn-postgres-pitr-tool-runner"),
    Path("/usr/local/sbin/mvn_postgres_pitr_operation_guard.py"),
)
PHASE_UNITS = {
    "wal-upload": "mvn-postgres-wal-upload.service",
    "basebackup": "mvn-postgres-basebackup.service",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OPERATION_RE = re.compile(r"^[0-9a-f]{32}$")
MAX_RELEASE_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_RELEASE_ASSET_BYTES = 1024 * 1024
BASE_RELEASE_MODES = {
    "/usr/local/sbin/mvn-postgres-pitr-upload": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-immutable-upload": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-upload-wal": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-basebackup": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-configure-env": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-provision-host": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_config_transaction.py": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-restore": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-restore-drill": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-status": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-remote-status": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-bootstrap": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-runtime-check": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-scheduled-runner": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-manual-runner": 0o755,
    "/usr/local/sbin/mvn-restore-drill-latest-db": 0o755,
    "/usr/local/sbin/mvn-restore-drill-latest-db-cleanup": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-tool-runner": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-artifact-security": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-wal-lineage": 0o755,
    "/usr/local/sbin/mvn-postgres-pitr-recovery-config": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py": 0o755,
    "/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py": 0o755,
    "/usr/local/libexec/mvn-pitr/install_postgres_pitr_units.sh": 0o755,
    "/usr/local/libexec/mvn-pitr/run_postgres_pitr_install_locked.py": 0o755,
    "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green.sh": 0o755,
    "/usr/local/libexec/mvn-pitr/deploy_backend_blue_green_safety.sh": 0o755,
    "/usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh": 0o755,
    "/etc/systemd/system/mvn-postgres-wal-upload.service": 0o644,
    "/etc/systemd/system/mvn-postgres-wal-upload.timer": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.service": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.timer": 0o644,
}


class LockBusyError(RuntimeError):
    """The shared PITR lock is already owned by another operation."""


def _validate_helper(path: Path) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o755
    ):
        raise RuntimeError(f"scheduled PITR helper metadata is unsafe: {path}")


def _open_owned_lock(path: Path, *, busy_message: str, shared: bool = False) -> int:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required lock protection is unavailable")
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise RuntimeError("shared PITR lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    try:
        operation = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
        fcntl.flock(descriptor, operation | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise LockBusyError(busy_message) from exc
    return descriptor


def _open_lock(path: Path = LOCK_PATH) -> int:
    return _open_owned_lock(
        path,
        busy_message="another PITR host operation is active",
        shared=True,
    )


def _reject_maintenance_marker() -> None:
    try:
        MAINTENANCE_MARKER.lstat()
    except FileNotFoundError:
        return
    raise RuntimeError("PITR release maintenance marker is present")


def _read_attested_file(path: Path, *, mode: int, limit: int) -> bytes:
    before = path.lstat()
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != 0
        or before.st_gid != 0
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != mode
        or before.st_size > limit
    ):
        raise RuntimeError(f"unsafe finalized PITR release file: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        identity = (
            "st_dev",
            "st_ino",
            "st_mode",
            "st_uid",
            "st_gid",
            "st_nlink",
            "st_size",
            "st_mtime_ns",
            "st_ctime_ns",
        )
        if tuple(getattr(opened, name) for name in identity) != tuple(
            getattr(before, name) for name in identity
        ):
            raise RuntimeError(f"finalized PITR release file changed while opening: {path}")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(131072, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > limit:
                raise RuntimeError(f"finalized PITR release file is too large: {path}")
        after = os.fstat(descriptor)
        if tuple(getattr(after, name) for name in identity) != tuple(
            getattr(opened, name) for name in identity
        ):
            raise RuntimeError(f"finalized PITR release file changed while reading: {path}")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _attest_finalized_release(project_dir: str, compose_file: str) -> str:
    modes = {
        **BASE_RELEASE_MODES,
        f"{project_dir}/{compose_file}": 0o644,
    }
    raw = _read_attested_file(
        RELEASE_MANIFEST,
        mode=0o600,
        limit=MAX_RELEASE_MANIFEST_BYTES,
    )
    try:
        manifest = json.loads(raw)
        canonical = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("ascii")
            + b"\n"
        )
    except (UnicodeDecodeError, UnicodeEncodeError, ValueError) as exc:
        raise RuntimeError("finalized PITR release manifest is invalid") from exc
    if raw != canonical or not isinstance(manifest, dict) or set(manifest) != {
        "files",
        "project_dir",
        "release_sha256",
        "txid",
        "version",
    }:
        raise RuntimeError("finalized PITR release manifest is not canonical")
    release = manifest.get("release_sha256")
    if (
        type(manifest.get("version")) is not int
        or manifest["version"] != 1
        or manifest.get("project_dir") != project_dir
        or not isinstance(manifest.get("txid"), str)
        or not OPERATION_RE.fullmatch(manifest["txid"])
        or not isinstance(release, str)
        or not SHA256_RE.fullmatch(release)
        or not isinstance(manifest.get("files"), list)
    ):
        raise RuntimeError("finalized PITR release manifest contract is invalid")
    files = manifest["files"]
    if len(files) != len(modes):
        raise RuntimeError("finalized PITR release path set is incomplete")
    for item, expected_path in zip(files, sorted(modes), strict=True):
        if (
            not isinstance(item, dict)
            or set(item) != {"mode", "path", "sha256"}
            or item.get("path") != expected_path
            or item.get("mode") != modes[expected_path]
            or not isinstance(item.get("sha256"), str)
            or not SHA256_RE.fullmatch(item["sha256"])
        ):
            raise RuntimeError("finalized PITR release file contract is invalid")
        content = _read_attested_file(
            Path(expected_path),
            mode=modes[expected_path],
            limit=MAX_RELEASE_ASSET_BYTES,
        )
        if hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise RuntimeError(f"finalized PITR release hash mismatch: {expected_path}")
    return release


def run_scheduled(
    *,
    phase: str,
    project_dir: str,
    compose_file: str,
    lock_path: Path = LOCK_PATH,
) -> int:
    if os.geteuid() != 0:
        raise RuntimeError("root execution is required")
    if ALLOWED_TARGETS.get(project_dir) != compose_file:
        raise RuntimeError("unreviewed scheduled PITR target")
    helper = PHASE_HELPERS.get(phase)
    if helper is None:
        raise RuntimeError("unsupported scheduled PITR phase")
    descriptor = _open_lock(lock_path)
    try:
        deploy_descriptor = _open_owned_lock(
            Path(project_dir) / ".deploy.lock",
            busy_message="another deploy or PITR project operation is active",
        )
        try:
            _reject_maintenance_marker()
            reconcile_project_operations(project_dir)
            _attest_finalized_release(project_dir, compose_file)
            for path in (*COMMON_HELPERS, helper):
                _validate_helper(path)
            environment = {
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME": "/root",
                "LANG": "C",
                "LC_ALL": "C",
                "DOCKER_CONTEXT": "default",
                "PROJECT_DIR": project_dir,
                "COMPOSE_FILE": compose_file,
            }
            return run_guarded_process(
                ["/bin/bash", str(helper)],
                environment=environment,
                phase=phase,
                project_dir=project_dir,
                kind="scheduled",
                unit=PHASE_UNITS[phase],
                record_command=str(helper),
                timeout_seconds=None,
            )
        finally:
            os.close(deploy_descriptor)
    finally:
        os.close(descriptor)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(PHASE_HELPERS), required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--compose-file", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    os.umask(0o077)
    try:
        return run_scheduled(
            phase=args.phase,
            project_dir=args.project_dir,
            compose_file=args.compose_file,
        )
    except LockBusyError as exc:
        print(f"scheduled PITR runner: {exc}", file=sys.stderr)
        return 75
    except (OSError, RuntimeError) as exc:
        print(f"scheduled PITR runner: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
