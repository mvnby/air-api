#!/usr/bin/env python3
"""Root-owned lifecycle records and cleanup for privileged PITR operations."""

from __future__ import annotations

import json
import importlib.util
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Mapping, Sequence


RECORD_ROOT = Path("/run/mvn-postgres-pitr-operations")
OPERATION_RE = re.compile(r"^[0-9a-f]{32}$")
ALLOWED_PROJECT_DIRS = {"/opt/air-api", "/opt/mvn-reserve"}
ALLOWED_PHASES = {
    "preflight",
    "provision-node",
    "configure-node",
    "scrub-node",
    "basebackup",
    "enable-archive-env",
    "enable-timers",
    "verify",
    "restore-drill",
    "logical-restore-drill",
    "wal-upload",
}
ALLOWED_COMMANDS = {
    "/usr/local/sbin/mvn-postgres-pitr-bootstrap",
    "/usr/local/sbin/mvn-postgres-pitr-upload-wal",
    "/usr/local/sbin/mvn-postgres-pitr-basebackup",
    "/usr/local/sbin/mvn-restore-drill-latest-db",
}
SCHEDULED_UNITS = {
    "mvn-postgres-wal-upload.service",
    "mvn-postgres-basebackup.service",
}
STANDBY_SAFE_PHASES = frozenset({"logical-restore-drill"})
CLEAN_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "HOME": "/root",
    "LANG": "C",
    "LC_ALL": "C",
    "DOCKER_CONTEXT": "default",
}


try:
    from scripts.ha.pitr_operation_cleanup import (
        cleanup_operation_artifacts,
        reconcile_orphan_artifacts,
    )
except ModuleNotFoundError:  # Installed host execution.
    cleanup_path = Path("/usr/local/sbin/mvn_postgres_pitr_operation_cleanup.py")
    cleanup_metadata = cleanup_path.lstat()
    if (
        stat.S_ISLNK(cleanup_metadata.st_mode)
        or not stat.S_ISREG(cleanup_metadata.st_mode)
        or cleanup_metadata.st_uid != 0
        or cleanup_metadata.st_gid != 0
        or cleanup_metadata.st_nlink != 1
        or stat.S_IMODE(cleanup_metadata.st_mode) != 0o755
    ):
        raise RuntimeError("installed PITR operation cleanup helper is unsafe")
    cleanup_spec = importlib.util.spec_from_file_location(
        "mvn_postgres_pitr_operation_cleanup", cleanup_path
    )
    if cleanup_spec is None or cleanup_spec.loader is None:
        raise RuntimeError("installed PITR operation cleanup helper could not be loaded")
    cleanup_module = importlib.util.module_from_spec(cleanup_spec)
    sys.modules[cleanup_spec.name] = cleanup_module
    cleanup_spec.loader.exec_module(cleanup_module)
    cleanup_operation_artifacts = cleanup_module.cleanup_operation_artifacts
    reconcile_orphan_artifacts = cleanup_module.reconcile_orphan_artifacts

PARENT_BOUND_LAUNCHER = (
    "import ctypes,os,signal,sys; "
    "expected=int(sys.argv[1]); "
    "expected > 1 or os._exit(125); "
    "os.getppid() == expected or os._exit(125); "
    "ctypes.CDLL(None, use_errno=True).prctl(1, signal.SIGKILL, 0, 0, 0) == 0 "
    "or (_ for _ in ()).throw(OSError(ctypes.get_errno(), 'prctl')); "
    "os.getppid() == expected or os._exit(125); "
    "fd=int(sys.argv[2]); token=os.read(fd,1); os.close(fd); "
    "token == b'1' or (_ for _ in ()).throw(RuntimeError('invalid launch barrier')); "
    "os.getppid() == expected or os._exit(125); "
    "os.execvpe(sys.argv[3], sys.argv[3:], os.environ)"
)


@dataclass(frozen=True)
class OperationRecord:
    operation_id: str
    kind: str
    phase: str
    project_dir: str
    pid: int
    pgid: int
    start_time: str
    command: str
    unit: str

    @property
    def path(self) -> Path:
        return RECORD_ROOT / f"{self.operation_id}.json"


class OperationInterrupted(Exception):
    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


def _validate_record(record: OperationRecord) -> None:
    if not OPERATION_RE.fullmatch(record.operation_id):
        raise RuntimeError("PITR operation ID is invalid")
    if record.kind not in {"manual", "scheduled"}:
        raise RuntimeError("PITR operation kind is invalid")
    if record.phase not in ALLOWED_PHASES:
        raise RuntimeError("PITR operation phase is invalid")
    if record.project_dir not in ALLOWED_PROJECT_DIRS:
        raise RuntimeError("PITR operation project is unreviewed")
    if record.pid <= 1 or record.pgid != record.pid:
        raise RuntimeError("PITR operation process identity is invalid")
    if not re.fullmatch(r"[0-9]+", record.start_time):
        raise RuntimeError("PITR operation start time is invalid")
    if record.command not in ALLOWED_COMMANDS:
        raise RuntimeError("PITR operation command is unreviewed")
    manual_unit = f"mvn-postgres-pitr-manual-{record.operation_id}.service"
    if record.kind == "manual":
        if record.unit not in {"", manual_unit}:
            raise RuntimeError("manual PITR operation unit is invalid")
    elif record.unit not in SCHEDULED_UNITS:
        raise RuntimeError("scheduled PITR operation unit is invalid")


def process_start_time(pid: int) -> str:
    payload = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    separator = payload.rfind(")")
    if separator < 0:
        raise RuntimeError("PITR process stat is invalid")
    fields = payload[separator + 1 :].split()
    if len(fields) <= 19 or not fields[19].isdigit():
        raise RuntimeError("PITR process start time is invalid")
    return fields[19]


def _process_cmdline(pid: int, *, limit: int = 65536) -> list[str]:
    descriptor = os.open(f"/proc/{pid}/cmdline", os.O_RDONLY | os.O_CLOEXEC)
    try:
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, min(4096, limit + 1 - len(payload)))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > limit:
                raise RuntimeError("PITR process command line is unexpectedly large")
    finally:
        os.close(descriptor)
    try:
        return [part.decode("utf-8") for part in bytes(payload).split(b"\0") if part]
    except UnicodeDecodeError as exc:
        raise RuntimeError("PITR process command line is invalid") from exc


def _validate_record_root(*, create: bool) -> None:
    if create:
        RECORD_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        metadata = RECORD_ROOT.lstat()
    except FileNotFoundError:
        if create:
            raise
        return
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        raise RuntimeError("PITR operation record directory metadata is unsafe")


def _fsync_record_root() -> None:
    descriptor = os.open(RECORD_ROOT, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_record(record: OperationRecord) -> None:
    _validate_record(record)
    _validate_record_root(create=True)
    temporary = RECORD_ROOT / f".{record.operation_id}.{os.getpid()}.tmp"
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    payload = (json.dumps(asdict(record), sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise RuntimeError("PITR operation record write made no progress")
            offset += written
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    finally:
        os.close(descriptor)
    if record.path.exists():
        temporary.unlink(missing_ok=True)
        raise RuntimeError("PITR operation record already exists")
    os.replace(temporary, record.path)
    _fsync_record_root()


def _read_record(path: Path) -> tuple[OperationRecord, tuple[int, int]]:
    if path.parent != RECORD_ROOT or not re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
        raise RuntimeError("PITR operation record path is invalid")
    before = path.lstat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != 0
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size > 4096
    ):
        raise RuntimeError("PITR operation record metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
            raise RuntimeError("PITR operation record changed while opening")
        payload = bytearray()
        while True:
            chunk = os.read(descriptor, 4097 - len(payload))
            if not chunk:
                break
            payload.extend(chunk)
            if len(payload) > 4096:
                raise RuntimeError("PITR operation record is unexpectedly large")
        finished = os.fstat(descriptor)
        if (
            finished.st_size,
            finished.st_mtime_ns,
            finished.st_ctime_ns,
        ) != (opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns):
            raise RuntimeError("PITR operation record changed while reading")
    finally:
        os.close(descriptor)
    try:
        raw = json.loads(bytes(payload))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("PITR operation record JSON is invalid") from exc
    expected_keys = set(OperationRecord.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) != expected_keys:
        raise RuntimeError("PITR operation record has an unexpected schema")
    if (
        any(not isinstance(raw[key], str) for key in expected_keys - {"pid", "pgid"})
        or type(raw["pid"]) is not int
        or type(raw["pgid"]) is not int
    ):
        raise RuntimeError("PITR operation record field types are invalid")
    record = OperationRecord(**raw)
    _validate_record(record)
    if path != record.path:
        raise RuntimeError("PITR operation record ID does not match its path")
    return record, (before.st_dev, before.st_ino)


def list_records(*, project_dir: str | None = None) -> list[OperationRecord]:
    _validate_record_root(create=False)
    if not RECORD_ROOT.exists():
        return []
    paths = sorted(
        path
        for path in RECORD_ROOT.iterdir()
        if re.fullmatch(r"[0-9a-f]{32}\.json", path.name)
    )
    if len(paths) > 32:
        raise RuntimeError("too many PITR operation records")
    records: list[OperationRecord] = []
    for path in paths:
        try:
            records.append(_read_record(path)[0])
        except FileNotFoundError:
            continue
    if project_dir is not None:
        records = [record for record in records if record.project_dir == project_dir]
    return records


def remove_record(record: OperationRecord, *, missing_ok: bool = False) -> None:
    try:
        current, identity = _read_record(record.path)
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if current != record:
        raise RuntimeError("PITR operation record generation changed")
    try:
        final = record.path.lstat()
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    if (final.st_dev, final.st_ino) != identity:
        raise RuntimeError("PITR operation record changed before removal")
    try:
        record.path.unlink()
    except FileNotFoundError:
        if missing_ok:
            return
        raise
    _fsync_record_root()


def _run(args: Sequence[str], *, timeout: float = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        env=CLEAN_ENV,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _pid_matches(record: OperationRecord) -> bool:
    try:
        if process_start_time(record.pid) != record.start_time:
            return False
        if os.getpgid(record.pid) != record.pgid:
            return False
        command_line = _process_cmdline(record.pid)
    except (FileNotFoundError, ProcessLookupError):
        return False
    return record.command in command_line


def _unit_active(unit: str) -> bool:
    if not unit:
        return False
    result = _run(
        [
            "systemctl",
            "show",
            "--property=LoadState,ActiveState,ControlGroup",
            unit,
        ],
        timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("could not inspect PITR operation systemd unit")
    properties = {}
    for line in result.stdout.splitlines():
        if "=" in line:
            name, value = line.split("=", 1)
            properties[name] = value
    if properties.get("LoadState") == "not-found":
        return False
    if properties.get("LoadState") not in {"loaded", "masked"}:
        raise RuntimeError("PITR operation systemd unit load state is unknown")
    if properties.get("ActiveState") not in {"inactive", "failed", "dead"}:
        return True
    control_group = properties.get("ControlGroup", "")
    if not control_group:
        return False
    if not control_group.startswith("/") or ".." in control_group.split("/"):
        raise RuntimeError("PITR operation control group path is invalid")
    events = Path("/sys/fs/cgroup") / control_group.lstrip("/") / "cgroup.events"
    try:
        values = dict(
            line.split(None, 1)
            for line in events.read_text(encoding="utf-8").splitlines()
            if " " in line
        )
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as exc:
        raise RuntimeError("could not inspect PITR operation control group") from exc
    return values.get("populated") == "1"


def _process_group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_stopped(record: OperationRecord, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _process_group_alive(record.pgid) and not _unit_active(record.unit):
            return True
        time.sleep(0.1)
    return not _process_group_alive(record.pgid) and not _unit_active(record.unit)


def terminate_record(record: OperationRecord, *, term_timeout: float = 10) -> None:
    _validate_record(record)
    process_matches = _pid_matches(record)
    group_alive = _process_group_alive(record.pgid)
    if not record.unit and group_alive and not process_matches:
        raise RuntimeError("direct PITR process identity became ambiguous")
    if record.unit and _unit_active(record.unit):
        _run(
            ["systemctl", "kill", "--kill-whom=all", "--signal=SIGTERM", record.unit],
            timeout=10,
        )
        _run(["systemctl", "stop", "--no-block", record.unit], timeout=10)
    elif process_matches:
        os.killpg(record.pgid, signal.SIGTERM)
    if not _wait_stopped(record, timeout=term_timeout):
        if record.unit:
            _run(
                ["systemctl", "kill", "--kill-whom=all", "--signal=SIGKILL", record.unit],
                timeout=10,
            )
        elif process_matches and _process_group_alive(record.pgid):
            os.killpg(record.pgid, signal.SIGKILL)
        if not _wait_stopped(record, timeout=10):
            raise RuntimeError("PITR operation process group remained active")
    cleanup_operation_artifacts(record.operation_id)
    remove_record(record, missing_ok=True)


def finalize_record(record: OperationRecord, *, timeout: float = 5) -> None:
    _validate_record(record)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        group_stopped = not _process_group_alive(record.pgid)
        unit_stopped = record.kind == "scheduled" or not _unit_active(record.unit)
        if group_stopped and unit_stopped:
            cleanup_operation_artifacts(record.operation_id)
            remove_record(record, missing_ok=True)
            return
        time.sleep(0.1)
    raise RuntimeError("completed PITR operation left a live process group or unit")


def _cancel_project_operations(
    project_dir: str,
    *,
    preserve_standby_safe: bool,
) -> list[str]:
    if project_dir not in ALLOWED_PROJECT_DIRS:
        raise RuntimeError("unreviewed project directory for PITR cancellation")
    cancelled: list[str] = []
    for record in list_records(project_dir=project_dir):
        if preserve_standby_safe and record.phase in STANDBY_SAFE_PHASES:
            continue
        terminate_record(record)
        cancelled.append(record.operation_id)
    return cancelled


def cancel_project_operations(project_dir: str) -> list[str]:
    """Fence mutating work while preserving a standby-safe logical drill."""

    return _cancel_project_operations(
        project_dir,
        preserve_standby_safe=True,
    )


def cancel_all_project_operations(project_dir: str) -> list[str]:
    """Cancel every operation for exclusive administrative maintenance."""

    return _cancel_project_operations(
        project_dir,
        preserve_standby_safe=False,
    )


def reconcile_project_operations(project_dir: str) -> list[str]:
    if project_dir not in ALLOWED_PROJECT_DIRS:
        raise RuntimeError("unreviewed project directory for PITR reconciliation")
    cleaned: list[str] = []
    records = list_records()
    for record in records:
        if record.project_dir != project_dir:
            continue
        process_matches = _pid_matches(record)
        group_alive = _process_group_alive(record.pgid)
        unit_active = _unit_active(record.unit)
        if process_matches or unit_active:
            raise RuntimeError("an active PITR operation already owns this project")
        if group_alive:
            raise RuntimeError("stale PITR operation process identity is ambiguous")
        cleanup_operation_artifacts(record.operation_id)
        remove_record(record, missing_ok=True)
        cleaned.append(record.operation_id)
    remaining = list_records()
    if any(record.project_dir == project_dir for record in remaining):
        raise RuntimeError("PITR project records remained after reconciliation")
    protected_ids = {record.operation_id for record in remaining}
    for operation_id in reconcile_orphan_artifacts(protected_ids):
        if operation_id not in cleaned:
            cleaned.append(operation_id)
    return cleaned


def terminate_owned_child(record: OperationRecord, *, term_timeout: float = 10) -> None:
    _validate_record(record)
    if not _pid_matches(record):
        if _process_group_alive(record.pgid):
            raise RuntimeError("owned PITR child identity became ambiguous")
    else:
        os.killpg(record.pgid, signal.SIGTERM)
    deadline = time.monotonic() + term_timeout
    while time.monotonic() < deadline and _process_group_alive(record.pgid):
        time.sleep(0.1)
    if _process_group_alive(record.pgid):
        os.killpg(record.pgid, signal.SIGKILL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and _process_group_alive(record.pgid):
            time.sleep(0.1)
    if _process_group_alive(record.pgid):
        raise RuntimeError("owned PITR child process group remained active")
    cleanup_operation_artifacts(record.operation_id)
    remove_record(record, missing_ok=True)


def _cloexec_pipe() -> tuple[int, int]:
    """Create a close-on-exec pipe on Linux and portable audit hosts."""
    if hasattr(os, "pipe2"):
        return os.pipe2(os.O_CLOEXEC)
    read_fd, write_fd = os.pipe()
    try:
        os.set_inheritable(read_fd, False)
        os.set_inheritable(write_fd, False)
    except BaseException:
        os.close(read_fd)
        os.close(write_fd)
        raise
    return read_fd, write_fd


def run_guarded_process(
    args: Sequence[str],
    *,
    environment: Mapping[str, str],
    phase: str,
    project_dir: str,
    kind: str,
    unit: str,
    record_command: str,
    timeout_seconds: float | None,
    pass_fds: Sequence[int] = (),
    stdin_payload: bytes | bytearray | memoryview | None = None,
    operation_id: str | None = None,
) -> int:
    identifier = operation_id or secrets.token_hex(16)
    child_environment = dict(environment)
    child_environment["PITR_OPERATION_ID"] = identifier
    barrier_read, barrier_write = _cloexec_pipe()
    process = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            PARENT_BOUND_LAUNCHER,
            str(os.getpid()),
            str(barrier_read),
            *args,
        ],
        env=child_environment,
        pass_fds=(*pass_fds, barrier_read),
        start_new_session=True,
        stdin=subprocess.PIPE if stdin_payload is not None else None,
    )
    os.close(barrier_read)
    record = OperationRecord(
        operation_id=identifier,
        kind=kind,
        phase=phase,
        project_dir=project_dir,
        pid=process.pid,
        pgid=process.pid,
        start_time=process_start_time(process.pid),
        command=record_command,
        unit=unit,
    )
    try:
        write_record(record)
    except BaseException:
        os.close(barrier_write)
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
        raise
    try:
        if os.write(barrier_write, b"1") != 1:
            raise RuntimeError("could not release PITR operation launch barrier")
        if stdin_payload is not None:
            if process.stdin is None:
                raise RuntimeError("PITR operation stdin pipe is unavailable")
            process.stdin.write(stdin_payload)
            process.stdin.close()
    except BaseException:
        terminate_record(record, term_timeout=5)
        process.wait()
        raise
    finally:
        os.close(barrier_write)

    previous_handlers = {}

    def interrupt(signum: int, _frame: object) -> None:
        raise OperationInterrupted(signum)

    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, interrupt)
    try:
        try:
            return_code = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            for signum in previous_handlers:
                signal.signal(signum, signal.SIG_IGN)
            if record.kind == "scheduled":
                terminate_owned_child(record, term_timeout=30)
            else:
                terminate_record(record, term_timeout=30)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return 124
        except OperationInterrupted as exc:
            for signum in previous_handlers:
                signal.signal(signum, signal.SIG_IGN)
            if record.kind == "scheduled":
                terminate_owned_child(record, term_timeout=30)
            else:
                terminate_record(record, term_timeout=30)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return 128 + exc.signum
        finalize_record(record, timeout=5)
        return return_code
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
