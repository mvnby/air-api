"""Pinned asset-attestation program embedded in privileged PITR SSH calls."""

from __future__ import annotations


REMOTE_ASSET_ATTESTATION = r'''
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import time

EXPECTED_ASSET_MODES = {
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
    "/usr/local/sbin/mvn-logical-restore-resource-sizer": 0o755,
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
    "/usr/local/libexec/mvn-pitr/require_deploy_capacity.sh": 0o755,
    "/usr/local/libexec/mvn-pitr/verify_pitr_maintenance_marker.py": 0o755,
    "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py": 0o755,
    "/usr/local/libexec/mvn-pitr/prepare_google_oauth_token_dir.sh": 0o755,
    "/etc/systemd/system/mvn-postgres-wal-upload.service": 0o644,
    "/etc/systemd/system/mvn-postgres-wal-upload.timer": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.service": 0o644,
    "/etc/systemd/system/mvn-postgres-basebackup.timer": 0o644,
}


ALLOWED_COMPOSE_PATHS = {
    "/opt/air-api/docker-compose.patroni.yml",
    "/opt/mvn-reserve/docker-compose.patroni.yml",
}
ALLOWED_PROJECT_DIRS = {"/opt/air-api", "/opt/mvn-reserve"}
OPERATION_GUARD_PATH = "/usr/local/sbin/mvn_postgres_pitr_operation_guard.py"


def load_operation_guard():
    specification = importlib.util.spec_from_file_location(
        "mvn_postgres_pitr_operation_guard",
        OPERATION_GUARD_PATH,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("PITR operation guard could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def _transient_command(args, environment, operation_id, timeout_seconds):
    unit = f"mvn-postgres-pitr-manual-{operation_id}.service"
    command = [
        "systemd-run",
        f"--unit={unit}",
        "--collect",
        "--wait",
        "--pipe",
        "--quiet",
        "--property=Type=exec",
        "--property=KillMode=control-group",
        "--property=SendSIGKILL=yes",
        "--property=TimeoutStopSec=30s",
        f"--property=RuntimeMaxSec={timeout_seconds}s",
    ]
    for name in sorted(environment):
        command.append(f"--setenv={name}={environment[name]}")
    return [*command, "--", *args], unit


def run_bounded(
    args,
    *,
    environment,
    pass_fds,
    phase,
    project_dir,
    timeout_seconds,
    transient,
    record_command,
    stdin_payload=None,
    guard_module=None,
    operation_id=None,
):
    guard = guard_module or load_operation_guard()
    if guard.list_records(project_dir=project_dir):
        raise RuntimeError("another recorded PITR operation requires cleanup")
    if operation_id is None:
        operation_id = secrets.token_hex(16)
    elif re.fullmatch(r"[0-9a-f]{32}", operation_id) is None:
        raise RuntimeError("invalid PITR operation ID")
    launch_args = args
    unit = ""
    if transient:
        if pass_fds:
            raise RuntimeError("transient PITR jobs cannot inherit file descriptors")
        unit_environment = dict(environment)
        unit_environment["PITR_OPERATION_ID"] = operation_id
        launch_args, unit = _transient_command(
            args,
            unit_environment,
            operation_id,
            timeout_seconds,
        )
    return guard.run_guarded_process(
        launch_args,
        environment=environment,
        phase=phase,
        project_dir=project_dir,
        kind="manual",
        unit=unit,
        record_command=record_command,
        timeout_seconds=timeout_seconds,
        pass_fds=tuple(pass_fds),
        stdin_payload=stdin_payload,
        operation_id=operation_id,
    )


def open_deploy_lock(project_dir):
    if project_dir not in ALLOWED_PROJECT_DIRS:
        raise RuntimeError("unreviewed project directory for deploy lock")
    path = os.path.join(project_dir, ".deploy.lock")
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise RuntimeError("project deploy lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(descriptor)
        raise
    return descriptor


def attest_assets(raw_manifest, project_dir, compose_file):
    try:
        manifest = json.loads(raw_manifest)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("host asset manifest is invalid") from exc
    compose_path = os.path.join(project_dir, compose_file)
    if compose_path not in ALLOWED_COMPOSE_PATHS:
        raise RuntimeError("host asset manifest has an unexpected compose path")
    expected_modes = dict(EXPECTED_ASSET_MODES)
    expected_modes[compose_path] = 0o644
    if not isinstance(manifest, dict) or set(manifest) != set(expected_modes):
        raise RuntimeError("host asset manifest has an unexpected path set")
    for path, expected_mode in expected_modes.items():
        digest = manifest.get(path)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise RuntimeError(f"host asset digest is invalid: {path}")
        try:
            metadata = os.lstat(path)
        except FileNotFoundError as exc:
            raise RuntimeError(f"host asset is missing: {path}") from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != 0
            or metadata.st_nlink != 1
            or stat.S_IMODE(metadata.st_mode) != expected_mode
        ):
            raise RuntimeError(f"host asset metadata is unsafe: {path}")
        descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            opened = os.fstat(descriptor)
            if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
                raise RuntimeError(f"host asset changed during attestation: {path}")
            hasher = hashlib.sha256()
            while True:
                chunk = os.read(descriptor, 131072)
                if not chunk:
                    break
                hasher.update(chunk)
        finally:
            os.close(descriptor)
        if hasher.hexdigest() != digest:
            raise RuntimeError(f"host asset digest mismatch: {path}")
    return manifest
'''.strip()
