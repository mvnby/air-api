#!/usr/bin/env python3
"""Run the two reviewed manual PITR phases through the host operation guard."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Sequence

LOCK_PATH = Path("/run/lock/mvn-postgres-pitr-prerequisites.lock")
MAINTENANCE_MARKER = Path("/run/mvn-postgres-pitr-maintenance")
RELEASE_MANIFEST = Path("/var/lib/mvn-postgres-pitr/release-manifest.json")
SELF = Path("/usr/local/sbin/mvn-postgres-pitr-manual-runner")
BOOTSTRAP = Path("/usr/local/sbin/mvn-postgres-pitr-bootstrap")
LOGICAL_DRILL = Path("/usr/local/sbin/mvn-restore-drill-latest-db")
LOGICAL_CLEANUP = Path("/usr/local/sbin/mvn-restore-drill-latest-db-cleanup")
LOGICAL_STATE_ROOT = Path("/var/lib/mvn-postgres-pitr/logical-restore-drills")
OPERATION_GUARD = Path("/usr/local/sbin/mvn_postgres_pitr_operation_guard.py")
ALLOWED_TARGETS = {
    "/opt/air-api": "docker-compose.patroni.yml",
    "/opt/mvn-reserve": "docker-compose.patroni.yml",
}
PHASE_TIMEOUTS = {
    "verify": 1200.0,
    "restore-drill": 7200.0,
    "logical-restore-drill": 1200.0,
}
OPERATION_RE = re.compile(r"^[0-9a-f]{32}$")
BACKUP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
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
    "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py": 0o755,
    "/usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh": 0o755,
    "/etc/systemd/system/mvn-postgres-wal-upload.service": 0o644,
    "/etc/systemd/system/mvn-postgres-wal-upload.timer": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.service": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.timer": 0o644,
}
REQUIRED_HELPERS = (
    BOOTSTRAP,
    Path("/usr/local/sbin/mvn-postgres-pitr-runtime-check"),
    Path("/usr/local/sbin/mvn-postgres-pitr-status"),
    Path("/usr/local/sbin/mvn-postgres-pitr-restore-drill"),
    Path("/usr/local/sbin/mvn-postgres-pitr-tool-runner"),
    Path("/usr/local/sbin/mvn-postgres-pitr-upload"),
    Path("/usr/local/sbin/mvn-postgres-pitr-immutable-upload"),
    Path("/usr/local/sbin/mvn-postgres-pitr-remote-status"),
    Path("/usr/local/sbin/mvn-postgres-pitr-restore"),
    Path("/usr/local/sbin/mvn-postgres-pitr-artifact-security"),
    Path("/usr/local/sbin/mvn-postgres-pitr-wal-lineage"),
    Path("/usr/local/sbin/mvn-postgres-pitr-recovery-config"),
    OPERATION_GUARD,
    Path("/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py"),
    LOGICAL_DRILL,
    LOGICAL_CLEANUP,
)


def _validate_helper(path: Path) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o755
    ):
        raise RuntimeError(f"unsafe installed PITR helper: {path}")


def _validate_self() -> None:
    if Path(__file__).resolve() != SELF:
        raise RuntimeError("manual PITR runner is not executing from its installed path")
    _validate_helper(SELF)


def _validate_state_root(path: Path) -> None:
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_gid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError(f"unsafe manual PITR state directory: {path}")


def _load_operation_guard():
    specification = importlib.util.spec_from_file_location(
        "mvn_postgres_pitr_operation_guard", OPERATION_GUARD
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("manual PITR operation guard could not be loaded")
    guard_module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = guard_module
    specification.loader.exec_module(guard_module)
    return guard_module


def _open_lock(path: Path = LOCK_PATH) -> int:
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
        raise RuntimeError("unsafe shared PITR operation lock")
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BaseException:
        os.close(descriptor)
        raise
    return descriptor


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


def _attest_finalized_release(
    project_dir: str,
    compose_file: str,
    *,
    expected_release_sha256: str | None,
) -> str:
    if expected_release_sha256 is not None and not SHA256_RE.fullmatch(
        expected_release_sha256
    ):
        raise RuntimeError("expected PITR release digest is invalid")
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
        or (expected_release_sha256 is not None and release != expected_release_sha256)
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


def run_manual(
    *,
    phase: str,
    project_dir: str,
    compose_file: str,
    operation_id: str,
    expected_release_sha256: str,
    backup_id: str = "",
    target_time: str = "",
) -> int:
    if os.geteuid() != 0:
        raise RuntimeError("root execution is required")
    _validate_self()
    if phase not in PHASE_TIMEOUTS:
        raise RuntimeError("unsupported manual PITR phase")
    if ALLOWED_TARGETS.get(project_dir) != compose_file:
        raise RuntimeError("unreviewed manual PITR target")
    project = Path(project_dir)
    if (
        project.resolve() != project
        or not project.is_dir()
        or not (project / compose_file).is_file()
    ):
        raise RuntimeError("manual PITR target is not a canonical deployed project")
    if not OPERATION_RE.fullmatch(operation_id):
        raise RuntimeError("manual PITR operation id is invalid")
    if not SHA256_RE.fullmatch(expected_release_sha256):
        raise RuntimeError("manual PITR expected release digest is invalid")
    if backup_id and not BACKUP_ID_RE.fullmatch(backup_id):
        raise RuntimeError("manual PITR backup id is invalid")
    if target_time and not UTC_RE.fullmatch(target_time):
        raise RuntimeError("manual PITR target time is invalid")
    if phase != "restore-drill" and (backup_id or target_time):
        raise RuntimeError(f"{phase} does not accept restore selectors")

    shared_lock = _open_lock()
    try:
        deploy_lock = _open_lock(project / ".deploy.lock")
        try:
            _reject_maintenance_marker()
            for helper in REQUIRED_HELPERS:
                _validate_helper(helper)
            operation_guard = _load_operation_guard()
            operation_guard.reconcile_project_operations(project_dir)
            _attest_finalized_release(
                project_dir,
                compose_file,
                expected_release_sha256=expected_release_sha256,
            )
            if phase == "logical-restore-drill":
                _validate_state_root(LOGICAL_STATE_ROOT)
            environment = {
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "HOME": "/root",
                "LANG": "C",
                "LC_ALL": "C",
                "DOCKER_CONTEXT": "default",
                "PROJECT_DIR": project_dir,
                "COMPOSE_FILE": compose_file,
            }
            if phase == "logical-restore-drill":
                environment.update(
                    {
                        "DRILL_ROOT": str(LOGICAL_STATE_ROOT),
                        "RESTORE_DRILL_CLEANUP_SCRIPT": str(LOGICAL_CLEANUP),
                    }
                )
                command = [str(LOGICAL_DRILL)]
                record_command = str(LOGICAL_DRILL)
            else:
                environment.update(
                    {
                        "PITR_REQUIRED": "true",
                        "REQUIRE_WAL": "true",
                        "BACKUP_ID": backup_id,
                        "TARGET_TIME": target_time,
                    }
                )
                command = ["/bin/bash", str(BOOTSTRAP), phase]
                record_command = str(BOOTSTRAP)
            return operation_guard.run_guarded_process(
                command,
                environment=environment,
                phase=phase,
                project_dir=project_dir,
                kind="manual",
                unit="",
                record_command=record_command,
                timeout_seconds=PHASE_TIMEOUTS[phase],
                operation_id=operation_id,
            )
        finally:
            os.close(deploy_lock)
    finally:
        os.close(shared_lock)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=tuple(PHASE_TIMEOUTS), required=True)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--expected-release-sha256", required=True)
    parser.add_argument("--backup-id", default="")
    parser.add_argument("--target-time", default="")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    os.umask(0o077)
    try:
        return run_manual(
            phase=args.phase,
            project_dir=args.project_dir,
            compose_file=args.compose_file,
            operation_id=args.operation_id,
            expected_release_sha256=args.expected_release_sha256,
            backup_id=args.backup_id,
            target_time=args.target_time,
        )
    except (OSError, RuntimeError) as exc:
        print(f"manual PITR runner: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
