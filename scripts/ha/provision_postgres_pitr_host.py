#!/usr/bin/env python3
"""Idempotently provision the fixed host state required by PITR operations."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, Sequence


TRANSACTION_RE = re.compile(r"^[0-9a-f]{32}$")
ARCHIVABLE_WAL_RE = re.compile(
    r"^(?:[0-9A-F]{24}(?:\.partial)?|[0-9A-F]{24}\.[0-9A-F]{8}\.backup|[0-9A-F]{8}\.history)$"
)
WAL_SEGMENT_ARCHIVE_RE = re.compile(r"^[0-9A-F]{24}(?:\.partial)?$")
MAX_ARCHIVE_ENTRIES = 8192
WAL_SEGMENT_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
ARCHIVE_LOCK_NAME = ".mvn-pitr-archive.lock"
SYSTEMD_UNITS = (
    "mvn-postgres-wal-upload.timer",
    "mvn-postgres-basebackup.timer",
    "mvn-postgres-wal-upload.service",
    "mvn-postgres-basebackup.service",
)
TIMER_UNITS = SYSTEMD_UNITS[:2]
SERVICE_UNITS = SYSTEMD_UNITS[2:]
ROLE_AGENT_UNIT = "mvn-patroni-role-agent.service"
CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}
ALLOWED_TARGETS = {
    "/opt/air-api": ("docker-compose.patroni.yml", "mvn-api"),
    "/opt/mvn-reserve": ("docker-compose.patroni.yml", "zakup"),
}


@dataclass(frozen=True)
class ProvisionPaths:
    state_root: Path = Path("/var/lib/mvn-postgres-pitr")
    record_root: Path = Path("/run/mvn-postgres-pitr-operations")
    systemd_env: Path = Path("/etc/mvn-postgres-pitr.env")
    maintenance_marker: Path = Path("/run/mvn-postgres-pitr-maintenance")

    @property
    def receipt_root(self) -> Path:
        return self.state_root / "provision-receipts"


@dataclass(frozen=True)
class PostgresIdentity:
    uid: int
    gid: int
    image_id: str
    image_ref: str


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        env=CLEAN_ENV,
        text=True,
        capture_output=True,
        check=False,
        timeout=120,
    )


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_root_dir(path: Path, *, expected_uid: int, expected_gid: int) -> None:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_uid != expected_uid
        or metadata.st_gid != expected_gid
    ):
        raise RuntimeError(f"unsafe PITR state directory: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        os.fchmod(descriptor, 0o700)
        current = os.fstat(descriptor)
        if stat.S_IMODE(current.st_mode) != 0o700:
            raise RuntimeError(f"could not enforce PITR state directory mode: {path}")
    finally:
        os.close(descriptor)


def _read_controlled(path: Path, *, expected_uid: int, expected_gid: int, limit: int) -> bytes:
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size > limit
    ):
        raise RuntimeError(f"unsafe PITR control file: {path}")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError(f"PITR control file changed while opening: {path}")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(65536, limit + 1 - len(payload)))
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


def _require_maintenance_marker(
    path: Path,
    transaction_id: str,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    payload = _read_controlled(
        path,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        limit=33,
    )
    if payload != (transaction_id + "\n").encode("ascii"):
        raise RuntimeError("PITR maintenance marker belongs to another transaction")


def _atomic_write(
    path: Path,
    payload: bytes,
    *,
    expected_uid: int,
    expected_gid: int,
) -> None:
    descriptor, raw_temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError(f"short PITR control file write: {path}")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fchown(descriptor, expected_uid, expected_gid)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = -1
        os.replace(temporary, path)
        _fsync_dir(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _provision_archive(
    archive_dir: Path,
    *,
    archive_uid: int,
    archive_gid: int,
) -> None:
    try:
        archive_dir.mkdir(mode=0o700)
    except FileExistsError:
        pass
    metadata = archive_dir.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError("PITR WAL archive path is unsafe")
    directory_fd = os.open(
        archive_dir,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    try:
        os.fchown(directory_fd, archive_uid, archive_gid)
        os.fchmod(directory_fd, 0o700)
        lock_path = archive_dir / ARCHIVE_LOCK_NAME
        lock_fd = os.open(
            lock_path,
            os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW,
            0o600,
        )
        try:
            lock_metadata = os.fstat(lock_fd)
            if not stat.S_ISREG(lock_metadata.st_mode) or lock_metadata.st_nlink != 1:
                raise RuntimeError("unsafe PITR WAL archive lock")
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            published_lock = lock_path.lstat()
            if (published_lock.st_dev, published_lock.st_ino) != (
                lock_metadata.st_dev,
                lock_metadata.st_ino,
            ):
                raise RuntimeError("PITR WAL archive lock changed while acquiring it")
            os.fchown(lock_fd, archive_uid, archive_gid)
            os.fchmod(lock_fd, 0o600)
            os.fsync(lock_fd)

            with os.scandir(archive_dir) as entries:
                for count, entry in enumerate(entries, start=1):
                    if count > MAX_ARCHIVE_ENTRIES:
                        raise RuntimeError("PITR WAL archive contains too many entries")
                    if entry.name == ARCHIVE_LOCK_NAME:
                        item = entry.stat(follow_symlinks=False)
                        if (item.st_dev, item.st_ino) != (
                            lock_metadata.st_dev,
                            lock_metadata.st_ino,
                        ):
                            raise RuntimeError("PITR WAL archive lock generation changed")
                        continue
                    if not ARCHIVABLE_WAL_RE.fullmatch(entry.name):
                        raise RuntimeError(
                            f"PITR WAL archive contains an unexpected entry: {entry.name}"
                        )
                    item = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(item.st_mode) or item.st_nlink != 1:
                        raise RuntimeError(f"unsafe PITR WAL archive entry: {entry.name}")
                    if (
                        WAL_SEGMENT_ARCHIVE_RE.fullmatch(entry.name)
                        and item.st_size != WAL_SEGMENT_BYTES
                    ):
                        raise RuntimeError(f"invalid PITR WAL segment size: {entry.name}")
                    if item.st_size <= 0 or item.st_size > MAX_ARCHIVE_BYTES:
                        raise RuntimeError(f"invalid PITR WAL archive entry size: {entry.name}")
                    descriptor = os.open(
                        entry.path,
                        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                    )
                    try:
                        opened = os.fstat(descriptor)
                        if (opened.st_dev, opened.st_ino) != (item.st_dev, item.st_ino):
                            raise RuntimeError(f"PITR WAL archive entry changed: {entry.name}")
                        os.fchown(descriptor, archive_uid, archive_gid)
                        os.fchmod(descriptor, 0o600)
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
            _fsync_dir(archive_dir)
        finally:
            os.close(lock_fd)
    finally:
        os.close(directory_fd)


def _run_checked(runner: Runner, args: Sequence[str], *, label: str) -> str:
    result = runner(args)
    if result.returncode != 0:
        raise RuntimeError(f"host provisioning command failed: {label}")
    return result.stdout.strip()


def _attest_postgres_identity(
    *,
    project_dir: str,
    compose_file: str,
    expected_uid: int,
    expected_gid: int,
    runner: Runner,
) -> PostgresIdentity:
    compose_path = f"{project_dir}/{compose_file}"
    container_id = _run_checked(
        runner,
        [
            "docker",
            "compose",
            "--project-directory",
            project_dir,
            "-f",
            compose_path,
            "ps",
            "-q",
            "db",
        ],
        label="resolve managed PostgreSQL container",
    )
    if not re.fullmatch(r"[0-9a-f]{12,64}", container_id):
        raise RuntimeError("managed PostgreSQL container identity is invalid")

    inspect = _run_checked(
        runner,
        [
            "docker",
            "inspect",
            "--format",
            "{{.Image}}|{{.Config.Image}}|{{.HostConfig.UsernsMode}}|{{.Config.User}}",
            container_id,
        ],
        label="inspect PostgreSQL container identity",
    )
    fields = inspect.split("|")
    if len(fields) != 4:
        raise RuntimeError("PostgreSQL container inspection is ambiguous")
    image_id, image_ref, userns_mode, configured_user = fields
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image_id):
        raise RuntimeError("PostgreSQL container image identity is invalid")
    if not re.fullmatch(r"[^\s|]{1,430}@sha256:[0-9a-f]{64}", image_ref):
        raise RuntimeError("PostgreSQL container image reference is not immutable")
    if userns_mode not in {"", "host"}:
        raise RuntimeError("PostgreSQL container uses an unreviewed user namespace mode")
    if configured_user not in {"", "postgres", "70", "70:70", "postgres:postgres"}:
        raise RuntimeError("PostgreSQL container configured user is unreviewed")

    security_raw = _run_checked(
        runner,
        ["docker", "info", "--format", "{{json .SecurityOptions}}"],
        label="inspect Docker user namespace mode",
    )
    try:
        security_options = json.loads(security_raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Docker security options are invalid") from exc
    if (
        not isinstance(security_options, list)
        or any(not isinstance(value, str) for value in security_options)
        or any(
            marker in value.lower()
            for value in security_options
            for marker in ("userns", "rootless")
        )
    ):
        raise RuntimeError("Docker rootless or user namespace remapping is not reviewed for PITR")

    process_identity = _run_checked(
        runner,
        [
            "docker",
            "exec",
            container_id,
            "sh",
            "-ceu",
            'uid="$(id -u postgres)"; gid="$(id -g postgres)"; '
            'owner="$(stat -c \'%u:%g\' /proc/1)"; '
            'printf \'%s:%s|%s\\n\' "$uid" "$gid" "$owner"',
        ],
        label="inspect PostgreSQL process ownership",
    )
    expected = f"{expected_uid}:{expected_gid}|{expected_uid}:{expected_gid}"
    if process_identity != expected:
        raise RuntimeError("PostgreSQL UID/GID does not match the host archive mapping")
    return PostgresIdentity(
        uid=expected_uid,
        gid=expected_gid,
        image_id=image_id,
        image_ref=image_ref,
    )


def _require_role_agent_inactive(runner: Runner) -> None:
    try:
        result = runner(["systemctl", "is-active", ROLE_AGENT_UNIT])
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError("could not prove the Patroni role agent is inactive") from exc
    if result.returncode not in {0, 3} or result.stdout.strip() != "inactive":
        raise RuntimeError(
            "Patroni role agent must be exactly inactive before PITR provisioning"
        )


def _quiesce_units(runner: Runner) -> None:
    command_failures: list[str] = []

    def attempt(args: Sequence[str]) -> None:
        try:
            result = runner(args)
        except (OSError, subprocess.SubprocessError) as exc:
            command_failures.append(f"{' '.join(args[1:])}: {type(exc).__name__}")
            return
        if result.returncode != 0:
            command_failures.append(f"{' '.join(args[1:])}: rc={result.returncode}")

    for _ in range(2):
        for unit in TIMER_UNITS:
            attempt(["systemctl", "disable", "--now", unit])
        for unit in SERVICE_UNITS:
            attempt(["systemctl", "stop", unit])
        for unit in SYSTEMD_UNITS:
            attempt(["systemctl", "reset-failed", unit])
        attempt(["systemctl", "daemon-reload"])

    unsafe_states: list[str] = []
    for unit in TIMER_UNITS:
        try:
            result = runner(["systemctl", "is-enabled", unit])
        except (OSError, subprocess.SubprocessError) as exc:
            unsafe_states.append(f"{unit}=unknown:{type(exc).__name__}")
        else:
            if result.returncode not in {0, 1} or result.stdout.strip() != "disabled":
                unsafe_states.append(f"{unit}=enabled-or-unknown")
    for unit in SYSTEMD_UNITS:
        try:
            result = runner(["systemctl", "is-active", unit])
        except (OSError, subprocess.SubprocessError) as exc:
            unsafe_states.append(f"{unit}=unknown:{type(exc).__name__}")
        else:
            if result.returncode not in {0, 3} or result.stdout.strip() != "inactive":
                unsafe_states.append(f"{unit}=active-or-unknown")
    if unsafe_states:
        raise RuntimeError(
            "PITR units did not converge to a safe state: " + "; ".join(unsafe_states)
        )
    if command_failures:
        raise RuntimeError(
            "PITR unit convergence reached safe postconditions after command failures: "
            + "; ".join(command_failures)
        )


def _receipt_payload(
    *,
    transaction_id: str,
    node: str,
    project_dir: str,
    compose_file: str,
    systemd_env: bytes,
    postgres_identity: PostgresIdentity,
) -> bytes:
    value = {
        "compose_file": compose_file,
        "node": node,
        "project_dir": project_dir,
        "postgres_gid": postgres_identity.gid,
        "postgres_image_id": postgres_identity.image_id,
        "postgres_image_ref": postgres_identity.image_ref,
        "postgres_uid": postgres_identity.uid,
        "schema_version": 1,
        "systemd_env_sha256": hashlib.sha256(systemd_env).hexdigest(),
        "transaction_id": transaction_id,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"


def provision_host(
    *,
    project_dir: str,
    compose_file: str,
    transaction_id: str,
    paths: ProvisionPaths = ProvisionPaths(),
    runner: Runner = _run,
    expected_uid: int = 0,
    expected_gid: int = 0,
    archive_uid: int = 70,
    archive_gid: int = 70,
    allowed_targets: Mapping[str, tuple[str, str]] = ALLOWED_TARGETS,
) -> Path:
    if os.geteuid() != expected_uid or os.getegid() != expected_gid:
        raise RuntimeError("root execution is required")
    if not TRANSACTION_RE.fullmatch(transaction_id):
        raise RuntimeError("PITR provision transaction ID is invalid")
    target = allowed_targets.get(project_dir)
    if target is None or target[0] != compose_file:
        raise RuntimeError("unreviewed PITR provision target")
    project = Path(project_dir)
    if project.resolve() != project or not project.is_dir():
        raise RuntimeError("PITR provision project path is not canonical")
    compose_path = project / compose_file
    if not compose_path.is_file() or compose_path.is_symlink():
        raise RuntimeError("PITR provision Compose file is unsafe")
    _require_maintenance_marker(
        paths.maintenance_marker,
        transaction_id,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    postgres_identity = _attest_postgres_identity(
        project_dir=project_dir,
        compose_file=compose_file,
        expected_uid=archive_uid,
        expected_gid=archive_gid,
        runner=runner,
    )
    _require_role_agent_inactive(runner)

    _ensure_root_dir(paths.state_root, expected_uid=expected_uid, expected_gid=expected_gid)
    for name in (
        "basebackups",
        "restore-drills",
        "logical-restore-drills",
        "transactions",
        "transactions-receipts",
        "provision-receipts",
    ):
        _ensure_root_dir(
            paths.state_root / name,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    _ensure_root_dir(paths.record_root, expected_uid=expected_uid, expected_gid=expected_gid)
    _provision_archive(
        project / "postgres-wal-archive",
        archive_uid=archive_uid,
        archive_gid=archive_gid,
    )

    systemd_env = f"PROJECT_DIR={project_dir}\nCOMPOSE_FILE={compose_file}\n".encode("ascii")
    _atomic_write(
        paths.systemd_env,
        systemd_env,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    _quiesce_units(runner)

    receipt = paths.receipt_root / f"{transaction_id}-{target[1]}.json"
    expected_receipt = _receipt_payload(
        transaction_id=transaction_id,
        node=target[1],
        project_dir=project_dir,
        compose_file=compose_file,
        systemd_env=systemd_env,
        postgres_identity=postgres_identity,
    )
    try:
        current = _read_controlled(
            receipt,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
            limit=4096,
        )
    except FileNotFoundError:
        _atomic_write(
            receipt,
            expected_receipt,
            expected_uid=expected_uid,
            expected_gid=expected_gid,
        )
    else:
        if current != expected_receipt:
            raise RuntimeError("PITR provision receipt conflicts with this transaction")

    committed_env = _read_controlled(
        paths.systemd_env,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
        limit=4096,
    )
    if committed_env != systemd_env:
        raise RuntimeError("PITR systemd environment drifted during provisioning")
    _require_maintenance_marker(
        paths.maintenance_marker,
        transaction_id,
        expected_uid=expected_uid,
        expected_gid=expected_gid,
    )
    return receipt


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-dir", required=True)
    parser.add_argument("--compose-file", required=True)
    parser.add_argument("--transaction-id", required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    os.umask(0o077)
    try:
        receipt = provision_host(
            project_dir=args.project_dir,
            compose_file=args.compose_file,
            transaction_id=args.transaction_id,
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"PITR host provision: {exc}", file=sys.stderr)
        return 1
    print(f"pitr_host_provision status=passed receipt={receipt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
