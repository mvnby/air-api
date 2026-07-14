#!/usr/bin/env python3
"""Run attested PITR tools in a minimal container outside the API Compose app."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Mapping, Sequence


BACKEND_IMAGE_RE = re.compile(
    r"^ghcr\.io/mvnby/air-api/backend@sha256:[0-9a-f]{64}$"
)
OPERATION_RE = re.compile(r"^[0-9a-f]{32}$")
SYSTEM_IDENTIFIER_RE = re.compile(r"^[1-9][0-9]{15,19}$")
WAL_RE = re.compile(
    r"^(?:[0-9A-F]{24}|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)
LSN_RE = re.compile(r"^[0-9A-F]{1,8}/[0-9A-F]{1,8}$")
UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
RESTORE_POINT_RE = re.compile(r"^mvn_pitr_[0-9a-f]{32}$")
ARCHIVE_UID = 70
ARCHIVE_GID = 70
ARCHIVE_MODE = 0o700
ARCHIVE_FILE_MODE = 0o600
MAX_ARCHIVE_ENTRIES = 8192
SECRETS_FILE = Path("/etc/mvn-postgres-pitr.secrets.env")
STATE_ROOT = Path("/var/lib/mvn-postgres-pitr")
ALLOWED_ARCHIVE_DIRS = {
    Path("/opt/air-api/postgres-wal-archive"),
    Path("/opt/mvn-reserve/postgres-wal-archive"),
}
SECRET_KEYS = (
    "POSTGRES_PITR_CLUSTER",
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_ACCESS_KEY_ID",
    "POSTGRES_PITR_S3_SECRET_ACCESS_KEY",
    "POSTGRES_PITR_S3_KEY_PREFIX",
)
DESTINATION_KEYS = (
    "POSTGRES_PITR_S3_BUCKET",
    "POSTGRES_PITR_S3_ENDPOINT_URL",
    "POSTGRES_PITR_S3_REGION",
    "POSTGRES_PITR_S3_KEY_PREFIX",
)
EXPECTED_DESTINATION_FINGERPRINT = (
    "f7dce2229a1d299e9403d4eb639106727676e587b333745c792bff0eacb16f8d"
)
HELPERS = {
    "upload": (
        Path("/usr/local/sbin/mvn-postgres-pitr-upload"),
        "/run/mvn-pitr-tools/upload.py",
    ),
    "immutable-upload": (
        Path("/usr/local/sbin/mvn-postgres-pitr-immutable-upload"),
        "/run/mvn-pitr-tools/immutable_upload.py",
    ),
    "remote": (
        Path("/usr/local/sbin/mvn-postgres-pitr-remote-status"),
        "/run/mvn-pitr-tools/remote.py",
    ),
    "restore": (
        Path("/usr/local/sbin/mvn-postgres-pitr-restore"),
        "/run/mvn-pitr-tools/restore.py",
    ),
    "security": (
        Path("/usr/local/sbin/mvn-postgres-pitr-artifact-security"),
        "/run/mvn-pitr-tools/artifact_security.py",
    ),
    "lineage": (
        Path("/usr/local/sbin/mvn-postgres-pitr-wal-lineage"),
        "/run/mvn-pitr-tools/wal_lineage.py",
    ),
    "recovery-config": (
        Path("/usr/local/sbin/mvn-postgres-pitr-recovery-config"),
        "/run/mvn-pitr-tools/recovery_config.py",
    ),
}
DOCKER_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}


def _read_controlled(path: Path, *, mode: int, limit: int = 65536) -> bytes:
    if not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("required file protection is unavailable")
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != 0
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != mode
    ):
        raise RuntimeError(f"unsafe PITR control file metadata: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"PITR control file changed while opening: {path}")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(131072, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > limit:
                raise RuntimeError(f"PITR control file is too large: {path}")
        finished = os.fstat(descriptor)
        if (
            finished.st_size,
            finished.st_mtime_ns,
            finished.st_ctime_ns,
        ) != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
            raise RuntimeError(f"PITR control file changed while reading: {path}")
        return bytes(payload)
    finally:
        os.close(descriptor)


def _parse_secrets(payload: bytes) -> dict[str, str]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("PITR secrets file is not UTF-8") from exc
    values: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise RuntimeError("PITR secrets file contains an invalid line")
        name, value = line.split("=", 1)
        if name not in SECRET_KEYS or name in values or not value or value != value.strip():
            raise RuntimeError("PITR secrets file is not canonical")
        if any(character.isspace() for character in value):
            raise RuntimeError("PITR secrets file contains unsafe whitespace")
        values[name] = value
    if set(values) != set(SECRET_KEYS):
        raise RuntimeError("PITR secrets file does not contain the exact key set")
    if values["POSTGRES_PITR_CLUSTER"] != "mvn-api":
        raise RuntimeError("PITR secrets file has an unreviewed logical namespace")
    destination = "\n".join(values[name] for name in DESTINATION_KEYS) + "\n"
    if hashlib.sha256(destination.encode()).hexdigest() != EXPECTED_DESTINATION_FINGERPRINT:
        raise RuntimeError("PITR secrets file has an unreviewed destination")
    return values


def _validate_candidate_secret_fd(raw_path: str) -> int:
    match = re.fullmatch(r"/proc/self/fd/([0-9]+)", raw_path)
    if not match:
        raise RuntimeError("candidate PITR secrets must use an anonymous inherited fd")
    descriptor = int(match.group(1))
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or metadata.st_nlink != 0
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise RuntimeError("candidate PITR secret fd metadata is unsafe")
    required_seals = (
        fcntl.F_SEAL_WRITE
        | fcntl.F_SEAL_GROW
        | fcntl.F_SEAL_SHRINK
        | fcntl.F_SEAL_SEAL
    )
    if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != required_seals:
        raise RuntimeError("candidate PITR secret fd is not fully sealed")
    duplicate = os.dup(descriptor)
    try:
        os.lseek(duplicate, 0, os.SEEK_SET)
        payload = bytearray()
        while True:
            chunk = os.read(duplicate, min(65537 - len(payload), 65536))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > 65536:
                raise RuntimeError("candidate PITR secret fd is unexpectedly large")
        _parse_secrets(bytes(payload))
    finally:
        os.close(duplicate)
        os.lseek(descriptor, 0, os.SEEK_SET)
    return descriptor


def _validate_helper(name: str) -> tuple[Path, str]:
    host, container = HELPERS[name]
    _read_controlled(host, mode=0o755, limit=1024 * 1024)
    return host, container


def _validate_directory(path: Path, *, roots: set[Path]) -> Path:
    if not path.is_absolute():
        raise RuntimeError("PITR data directory must be absolute")
    resolved = path.resolve()
    if path != resolved:
        raise RuntimeError("PITR data directory must not contain symlinks")
    metadata = path.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_nlink < 2:
        raise RuntimeError("PITR data path is not a safe directory")
    if path in roots:
        return path
    for root in roots:
        if root == STATE_ROOT and root in path.parents:
            return path
    raise RuntimeError("PITR data directory is outside the reviewed roots")


def _validate_archive_directory(path: Path) -> tuple[Path, int, int]:
    directory = _validate_directory(path, roots=ALLOWED_ARCHIVE_DIRS)
    metadata = directory.lstat()
    if (
        metadata.st_uid != ARCHIVE_UID
        or metadata.st_gid != ARCHIVE_GID
        or stat.S_IMODE(metadata.st_mode) != ARCHIVE_MODE
    ):
        raise RuntimeError("PITR archive directory ownership or mode is unsafe")
    for count, entry in enumerate(os.scandir(directory), start=1):
        if count > MAX_ARCHIVE_ENTRIES:
            raise RuntimeError("PITR archive directory has too many entries")
        if entry.name != ".mvn-pitr-archive.lock" and not WAL_RE.fullmatch(entry.name):
            raise RuntimeError("PITR archive directory contains an unreviewed entry")
        item = entry.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(item.st_mode)
            or item.st_uid != ARCHIVE_UID
            or item.st_gid != ARCHIVE_GID
            or stat.S_IMODE(item.st_mode) != ARCHIVE_FILE_MODE
            or item.st_nlink != 1
        ):
            raise RuntimeError("PITR archive entry ownership or mode is unsafe")
        if len(entry.name) == 24 and item.st_size != 16 * 1024 * 1024:
            raise RuntimeError("PITR archive WAL segment size is invalid")
        if entry.name != ".mvn-pitr-archive.lock" and item.st_size <= 0:
            raise RuntimeError("PITR archive entry is empty")
    return directory, ARCHIVE_UID, ARCHIVE_GID


def _mount(source: Path, destination: str, *, readonly: bool) -> list[str]:
    specification = f"type=bind,src={source},dst={destination}"
    if readonly:
        specification += ",readonly"
    return ["--mount", specification]


def _base_command(
    image: str,
    *,
    operation_id: str,
    phase: str,
    secrets_path: Path = SECRETS_FILE,
    secrets_already_validated: bool = False,
) -> list[str]:
    if not BACKEND_IMAGE_RE.fullmatch(image):
        raise RuntimeError("BACKEND_IMAGE must be an immutable reviewed digest")
    if not OPERATION_RE.fullmatch(operation_id):
        raise RuntimeError("PITR_OPERATION_ID must be a guarded operation ID")
    if not secrets_already_validated:
        _parse_secrets(_read_controlled(secrets_path, mode=0o600))
    return [
        "docker",
        "run",
        "--rm",
        "--name",
        f"mvn-pitr-{phase}-{operation_id}",
        "--label",
        f"com.mvn.pitr.operation={operation_id}",
        "--label",
        f"com.mvn.pitr.phase={phase}",
        "--pull",
        "never",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges:true",
        "--pids-limit",
        "128",
        "--memory",
        "768m",
        "--network",
        "bridge",
        "--env-file",
        str(secrets_path),
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=64m,mode=0700",
    ]


def _tool_command(
    args: argparse.Namespace,
    image: str,
    *,
    operation_id: str,
    secrets_path: Path = SECRETS_FILE,
    secrets_already_validated: bool = False,
) -> list[str]:
    command = _base_command(
        image,
        operation_id=operation_id,
        phase=args.phase,
        secrets_path=secrets_path,
        secrets_already_validated=secrets_already_validated,
    )
    upload_host, upload_container = _validate_helper("upload")
    command += _mount(upload_host, upload_container, readonly=True)
    immutable_host, immutable_container = _validate_helper("immutable-upload")
    command += _mount(immutable_host, immutable_container, readonly=True)
    command += [
        "-e",
        f"POSTGRES_PITR_IMMUTABLE_UPLOAD_HELPER={immutable_container}",
    ]
    if args.phase == "credential-probe":
        if not OPERATION_RE.fullmatch(args.transaction_id):
            raise RuntimeError("PITR credential probe transaction id is invalid")
        if args.node not in {"mvn-api", "zakup"}:
            raise RuntimeError("PITR credential probe node is invalid")
        tool_args = [
            "python",
            "-I",
            upload_container,
            "probe",
            "--transaction-id",
            args.transaction_id,
            "--node",
            args.node,
        ]
    elif args.phase == "wal-upload":
        data, archive_uid, archive_gid = _validate_archive_directory(Path(args.data_dir))
        command += ["--user", f"{archive_uid}:{archive_gid}"]
        command += _mount(data, "/pitr-data", readonly=False)
        tool_args = ["python", "-I", upload_container, "wal", "--archive-dir", "/pitr-data"]
        if args.dry_run:
            tool_args.append("--dry-run")
        tool_args.append(
            "--delete-after-upload" if args.delete_after_upload else "--no-delete-after-upload"
        )
    elif args.phase == "basebackup-upload":
        data = _validate_directory(Path(args.data_dir), roots={STATE_ROOT})
        command += _mount(data, "/pitr-data", readonly=True)
        tool_args = [
            "python",
            "-I",
            upload_container,
            "basebackup",
            "--source-dir",
            "/pitr-data",
            "--backup-id",
            args.backup_id,
            "--system-identifier",
            args.system_identifier,
            "--timeline",
            args.timeline,
            "--start-lsn",
            args.start_lsn,
            "--end-lsn",
            args.end_lsn,
            "--started-at",
            args.started_at,
            "--completed-at",
            args.completed_at,
            "--source-node",
            args.source_node,
        ]
        if args.dry_run:
            tool_args.append("--dry-run")
    elif args.phase == "remote-status":
        remote_host, remote_container = _validate_helper("remote")
        command += _mount(remote_host, remote_container, readonly=True)
        command += ["-e", f"POSTGRES_PITR_UPLOAD_HELPER={upload_container}"]
        tool_args = [
            "python",
            "-I",
            remote_container,
            "--max-wal-age-minutes",
            args.max_wal_age_minutes,
            "--max-basebackup-age-hours",
            args.max_basebackup_age_hours,
            "--local-pending-wal-count",
            str(args.local_pending_wal_count),
        ]
        if not SYSTEM_IDENTIFIER_RE.fullmatch(args.expected_system_identifier):
            raise RuntimeError("expected PostgreSQL system identifier is invalid")
        tool_args += [
            "--expected-system-identifier",
            args.expected_system_identifier,
        ]
        if args.expected_wal:
            if not WAL_RE.fullmatch(args.expected_wal):
                raise RuntimeError("expected WAL name is invalid")
            tool_args += ["--expected-wal", args.expected_wal]
    else:
        data = _validate_directory(Path(args.data_dir), roots={STATE_ROOT})
        restore_host, restore_container = _validate_helper("restore")
        security_host, security_container = _validate_helper("security")
        lineage_host, lineage_container = _validate_helper("lineage")
        config_host, config_container = _validate_helper("recovery-config")
        command += _mount(restore_host, restore_container, readonly=True)
        command += _mount(security_host, security_container, readonly=True)
        command += _mount(lineage_host, lineage_container, readonly=True)
        command += _mount(config_host, config_container, readonly=True)
        command += _mount(data, "/pitr-data", readonly=False)
        command += [
            "-e",
            f"POSTGRES_PITR_UPLOAD_HELPER={upload_container}",
            "-e",
            f"POSTGRES_PITR_ARTIFACT_SECURITY_HELPER={security_container}",
            "-e",
            f"POSTGRES_PITR_WAL_LINEAGE_HELPER={lineage_container}",
            "-e",
            f"POSTGRES_PITR_RECOVERY_CONFIG_HELPER={config_container}",
        ]
        tool_args = [
            "python",
            "-I",
            restore_container,
            "prepare",
            "--target-dir",
            "/pitr-data",
            "--wal-mode",
            "local",
            "--restore-mount-path",
            "/pitr-restore",
        ]
        if not SYSTEM_IDENTIFIER_RE.fullmatch(args.expected_system_identifier):
            raise RuntimeError("expected PostgreSQL system identifier is invalid")
        if not re.fullmatch(r"[0-9A-F]{24}", args.required_end_wal):
            raise RuntimeError("required restore end WAL is invalid")
        tool_args += [
            "--expected-system-identifier",
            args.expected_system_identifier,
            "--required-end-wal",
            args.required_end_wal,
        ]
        if args.backup_id:
            tool_args += ["--backup-id", args.backup_id]
        if bool(args.target_time) == bool(args.target_name) or bool(args.target_name) != bool(args.target_lsn):
            raise RuntimeError("restore target selector is invalid")
        if args.target_time:
            if not UTC_RE.fullmatch(args.target_time):
                raise RuntimeError("restore target time is invalid")
            tool_args += ["--target-time", args.target_time]
        else:
            if not RESTORE_POINT_RE.fullmatch(args.target_name) or not LSN_RE.fullmatch(args.target_lsn):
                raise RuntimeError("restore point target is invalid")
            tool_args += ["--target-name", args.target_name, "--target-lsn", args.target_lsn]
    return [*command, image, *tool_args]


def run_tool(
    args: argparse.Namespace,
    *,
    environ: Mapping[str, str],
) -> int:
    if os.geteuid() != 0:
        raise RuntimeError("root execution is required")
    candidate_fd = None
    secrets_path = SECRETS_FILE
    if args.phase == "credential-probe":
        secrets_path = Path(environ.get("ENV_INPUT_FILE", ""))
        candidate_fd = _validate_candidate_secret_fd(str(secrets_path))
    command = _tool_command(
        args,
        environ.get("BACKEND_IMAGE", ""),
        operation_id=environ.get("PITR_OPERATION_ID", ""),
        secrets_path=secrets_path,
        secrets_already_validated=candidate_fd is not None,
    )
    result = subprocess.run(
        command,
        env=DOCKER_ENV,
        check=False,
        pass_fds=(candidate_fd,) if candidate_fd is not None else (),
    )
    return result.returncode


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=(
            "credential-probe",
            "wal-upload",
            "basebackup-upload",
            "remote-status",
            "restore-prepare",
        ),
        required=True,
    )
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--backup-id", default="")
    parser.add_argument("--system-identifier", default="")
    parser.add_argument("--timeline", default="")
    parser.add_argument("--start-lsn", default="")
    parser.add_argument("--end-lsn", default="")
    parser.add_argument("--started-at", default="")
    parser.add_argument("--completed-at", default="")
    parser.add_argument("--source-node", default="")
    parser.add_argument("--target-time", default="")
    parser.add_argument("--target-name", default="")
    parser.add_argument("--target-lsn", default="")
    parser.add_argument("--max-wal-age-minutes", default="180")
    parser.add_argument("--max-basebackup-age-hours", default="30")
    parser.add_argument("--local-pending-wal-count", type=int, default=0)
    parser.add_argument("--expected-wal", default="")
    parser.add_argument("--expected-system-identifier", default="")
    parser.add_argument("--required-end-wal", default="")
    parser.add_argument("--transaction-id", default="")
    parser.add_argument("--node", default="")
    parser.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument(
        "--delete-after-upload",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        return run_tool(parse_args(argv), environ=os.environ)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"pitr tool runner: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
