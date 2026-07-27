#!/usr/bin/env python3
"""Pinned, fail-closed communications drain before a PITR release cutover."""

from __future__ import annotations

import re
import shlex
import subprocess
from typing import Callable, Sequence

try:
    from scripts.ha.pitr_pinned_ssh import (
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_pinned_ssh import (  # type: ignore[no-redef]
        PatroniNode,
        PinnedSshContext,
        ssh_args,
    )


Runner = Callable[[Sequence[str], str | None], subprocess.CompletedProcess[str]]
TRANSACTION_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# This fragment is included in the separately pinned release executor. A
# receipt is accepted only with the exact release fence and either the matching
# marker or no marker (the durable marker-first cleanup crash window). It is
# removed when that release is finalized/rolled back. The communications
# release fence deliberately survives until the immediately following API
# deployment has re-verified the new profile.
REMOTE_COMMUNICATIONS_CUTOVER_RECEIPT_SUPPORT = r'''
COMMUNICATIONS_CUTOVER_RECEIPT_NAME = ".ha-communications-cutover-preflight"
COMMUNICATIONS_RELEASE_FENCE_NAME = ".ha-communications-worker-release-fenced"
def communications_cutover_receipt_path(project_dir):
    return os.path.join(project_dir, COMMUNICATIONS_CUTOVER_RECEIPT_NAME)
def communications_cutover_receipt_valid(project_dir, txid):
    try:
        content, _ = read_regular(
            communications_cutover_receipt_path(project_dir),
            exact_mode=0o600,
            max_bytes=96,
        )
    except FileNotFoundError:
        return False
    expected = ("communications-off-drained-v1\n" + txid + "\n").encode("ascii")
    if content != expected:
        raise RuntimeError(
            "communications cutover receipt belongs to another transaction"
        )
    try:
        fence, _ = read_regular(
            os.path.join(project_dir, COMMUNICATIONS_RELEASE_FENCE_NAME),
            exact_mode=0o600,
            max_bytes=16,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "communications cutover receipt is missing its release fence"
        ) from exc
    if fence != b"fenced\n":
        raise RuntimeError("communications cutover release fence is invalid")
    return True
def remove_communications_cutover_receipt(project_dir, txid):
    path = communications_cutover_receipt_path(project_dir)
    try:
        content, _ = read_regular(path, exact_mode=0o600, max_bytes=96)
    except FileNotFoundError:
        return
    if content != ("communications-off-drained-v1\n" + txid + "\n").encode("ascii"):
        raise RuntimeError("communications cutover receipt ownership changed")
    os.unlink(path)
    fsync_dir(project_dir)
'''.strip() + "\n"


REMOTE_COMMUNICATIONS_CUTOVER_PREFLIGHT = r'''
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile

ROOT_UID = ROOT_GID = 0
GLOBAL_LOCK = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
MAINTENANCE_MARKER = "/run/mvn-postgres-pitr-maintenance"
PROJECT_COMPOSE = {
    "/opt/air-api": "/opt/air-api/docker-compose.patroni.yml",
    "/opt/mvn-reserve": "/opt/mvn-reserve/docker-compose.patroni.yml",
}
RECEIPT_NAME = ".ha-communications-cutover-preflight"
RELEASE_FENCE_NAME = ".ha-communications-worker-release-fenced"
WORKER_SERVICE = "communications-worker"


def validate_parent(path):
    if not path.startswith("/") or os.path.normpath(path) != path:
        raise RuntimeError("communications cutover path is not canonical")
    current = "/"
    for part in os.path.dirname(path).split("/")[1:]:
        current = os.path.join(current, part)
        metadata = os.lstat(current)
        writable = stat.S_IMODE(metadata.st_mode) & 0o022
        sticky_lock_dir = (
            current == "/run/lock"
            and writable == 0o022
            and bool(metadata.st_mode & stat.S_ISVTX)
        )
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != ROOT_UID
            or metadata.st_gid != ROOT_GID
            or (writable and not sticky_lock_dir)
        ):
            raise RuntimeError("communications cutover parent metadata is unsafe")


def read_regular(path, *, exact_mode, max_bytes):
    before = os.lstat(path)
    if (
        not stat.S_ISREG(before.st_mode)
        or stat.S_ISLNK(before.st_mode)
        or before.st_uid != ROOT_UID
        or before.st_gid != ROOT_GID
        or before.st_nlink != 1
        or stat.S_IMODE(before.st_mode) != exact_mode
        or before.st_size > max_bytes
    ):
        raise RuntimeError("communications cutover file metadata is unsafe")
    descriptor = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        fields = (
            "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
            "st_size", "st_mtime_ns", "st_ctime_ns",
        )
        if tuple(getattr(opened, name) for name in fields) != tuple(
            getattr(before, name) for name in fields
        ):
            raise RuntimeError("communications cutover file changed while opening")
        payload = os.read(descriptor, max_bytes + 1)
        if len(payload) > max_bytes or os.read(descriptor, 1):
            raise RuntimeError("communications cutover file is too large")
        after = os.fstat(descriptor)
        if tuple(getattr(after, name) for name in fields) != tuple(
            getattr(opened, name) for name in fields
        ):
            raise RuntimeError("communications cutover file changed while reading")
        return payload
    finally:
        os.close(descriptor)


def atomic_write(path, content, mode):
    validate_parent(path)
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        pass
    else:
        if (
            not stat.S_ISREG(existing.st_mode)
            or stat.S_ISLNK(existing.st_mode)
            or existing.st_uid != ROOT_UID
            or existing.st_gid != ROOT_GID
            or existing.st_nlink != 1
        ):
            raise RuntimeError("communications cutover target metadata is unsafe")
    descriptor, temporary = tempfile.mkstemp(
        prefix=".mvn-communications-cutover-",
        dir=os.path.dirname(path),
    )
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        if os.write(descriptor, content) != len(content):
            raise RuntimeError("short communications cutover write")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        os.replace(temporary, path)
        directory = os.open(
            os.path.dirname(path),
            os.O_RDONLY | os.O_CLOEXEC | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def open_lock(path):
    validate_parent(path)
    descriptor = os.open(
        path,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or metadata.st_nlink != 1
        or metadata.st_mode & 0o022
    ):
        os.close(descriptor)
        raise RuntimeError("communications cutover lock metadata is unsafe")
    os.fchmod(descriptor, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise RuntimeError("another PITR or deploy operation is active") from exc
    return descriptor


def run_checked(args, *, timeout, capture=True):
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C",
        "LC_ALL": "C",
    }
    result = subprocess.run(
        args,
        env=environment,
        stdin=subprocess.DEVNULL,
        text=True,
        capture_output=capture,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError("communications cutover command failed")
    return result


def prove_operator_off_drained(compose_path, app_service):
    command = run_checked(
        [
            "docker", "compose", "-f", compose_path, "--profile", "bluegreen",
            "exec", "-T", app_service, "python3",
            "scripts/communications_installation_notifications.py", "--off",
        ],
        timeout=90,
    )
    if command.stderr or len(command.stdout.splitlines()) != 1:
        raise RuntimeError("communications off command returned unsafe output")
    try:
        result = json.loads(command.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("communications off receipt is invalid") from exc
    if (
        not isinstance(result, dict)
        or result.get("ok") is not True
        or result.get("command") != "off"
        or result.get("drained") is not True
        or result.get("runtime_mode") != "off"
        or result.get("runtime_status")
        not in {"disabled", "stopped", "paused", "faulted"}
        or type(result.get("running_delivery_count")) is not int
        or result.get("running_delivery_count") != 0
        or type(result.get("control_revision")) is not int
        or result.get("control_revision") < 0
    ):
        raise RuntimeError("communications runtime did not prove off and drained")


def prove_worker_zero_running(compose_path):
    running = run_checked(
        [
            "docker", "compose", "-f", compose_path, "--profile", "bluegreen",
            "ps", "--status", "running", "-q", WORKER_SERVICE,
        ],
        timeout=30,
    )
    if running.stdout or running.stderr:
        raise RuntimeError("communications worker remained running")


def execute(txid, project_dir, compose_file):
    if os.geteuid() != ROOT_UID or not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("root Linux execution is required")
    if re.fullmatch(r"[0-9a-f]{32}", txid) is None:
        raise RuntimeError("transaction id must be 32 lowercase hexadecimal characters")
    compose_path = PROJECT_COMPOSE.get(project_dir)
    if compose_path != os.path.join(project_dir, compose_file):
        raise RuntimeError("unreviewed communications cutover node")
    read_regular(compose_path, exact_mode=0o644, max_bytes=1048576)
    deploy_lock = os.path.join(project_dir, ".deploy.lock")
    global_fd = open_lock(GLOBAL_LOCK)
    deploy_fd = None
    try:
        deploy_fd = open_lock(deploy_lock)
        marker_txid = None
        try:
            marker = read_regular(
                MAINTENANCE_MARKER, exact_mode=0o600, max_bytes=34
            )
            marker_text = marker.decode("ascii")
            if re.fullmatch(r"[0-9a-f]{32}\n", marker_text) is None:
                raise RuntimeError("PITR maintenance marker is invalid")
            marker_txid = marker_text[:-1]
        except FileNotFoundError:
            pass
        if marker_txid is not None and marker_txid != txid:
            raise RuntimeError("another PITR release owns the maintenance marker")

        receipt_path = os.path.join(project_dir, RECEIPT_NAME)
        receipt = ("communications-off-drained-v1\n" + txid + "\n").encode("ascii")
        try:
            prior_receipt = read_regular(
                receipt_path, exact_mode=0o600, max_bytes=96
            )
        except FileNotFoundError:
            prior_receipt = None
        if prior_receipt is not None and prior_receipt != receipt:
            raise RuntimeError("another communications cutover receipt is active")
        if marker_txid == txid and prior_receipt != receipt:
            raise RuntimeError("PITR marker lacks its communications cutover receipt")

        rendered = run_checked(
            [
                "docker", "compose", "-f", compose_path, "--profile", "bluegreen",
                "config", "--format", "json",
            ],
            timeout=30,
        )
        try:
            payload = json.loads(rendered.stdout)
            services = payload.get("services") or {}
            worker = services.get(WORKER_SERVICE)
            environment = worker.get("environment") if isinstance(worker, dict) else None
            gates = (
                environment.get("COMMUNICATIONS_WORKER_ENABLED"),
                environment.get("COMMUNICATIONS_WORKER_ALLOW_ALL_MODE"),
            )
        except (AttributeError, json.JSONDecodeError) as exc:
            raise RuntimeError("communications worker profile is unavailable") from exc
        if gates not in {
            ("false", "false"),
            ("true", "false"),
            ("true", "true"),
        }:
            raise RuntimeError("communications worker profile is not reviewed")

        active_slot_path = os.path.join(project_dir, ".active-api-slot")
        try:
            active_slot = read_regular(
                active_slot_path, exact_mode=0o600, max_bytes=8
            ).decode("ascii")
        except FileNotFoundError:
            app_service = "app"
        else:
            if active_slot not in {"blue\n", "green\n"}:
                raise RuntimeError("active API slot is invalid")
            app_service = "app-" + active_slot.strip()

        prove_operator_off_drained(compose_path, app_service)

        fence_path = os.path.join(project_dir, RELEASE_FENCE_NAME)
        atomic_write(fence_path, b"fenced\n", 0o600)
        run_checked(
            [
                "docker", "compose", "-f", compose_path, "--profile", "bluegreen",
                "stop", WORKER_SERVICE,
            ],
            timeout=60,
        )
        prove_worker_zero_running(compose_path)

        # The first database proof may have become stale while the host worker
        # was being fenced. Re-issue the typed OFF command and repeat the
        # zero-running proof immediately before the durable receipt/marker.
        prove_operator_off_drained(compose_path, app_service)
        prove_worker_zero_running(compose_path)
        atomic_write(receipt_path, receipt, 0o600)
        atomic_write(MAINTENANCE_MARKER, (txid + "\n").encode("ascii"), 0o600)
    finally:
        if deploy_fd is not None:
            os.close(deploy_fd)
        os.close(global_fd)


if len(sys.argv) != 4:
    raise SystemExit("invalid communications cutover invocation")
try:
    execute(*sys.argv[1:])
except (OSError, RuntimeError, subprocess.SubprocessError, UnicodeError):
    print("communications cutover preflight failed", file=sys.stderr)
    raise SystemExit(1)
print("communications_cutover_preflight=verified")
'''.strip()


def run_remote_communications_cutover_preflight(
    *,
    node: PatroniNode,
    context: PinnedSshContext,
    transaction_id: str,
    runner: Runner,
) -> None:
    """Prove DB control is off/drained and durably fence worker activation."""

    if TRANSACTION_ID_RE.fullmatch(transaction_id) is None:
        raise RuntimeError(
            "PITR transaction ID must be 32 lowercase hexadecimal characters"
        )
    command = " ".join(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            shlex.quote(REMOTE_COMMUNICATIONS_CUTOVER_PREFLIGHT),
            transaction_id,
            shlex.quote(node.project_dir),
            shlex.quote(node.compose_file),
        ]
    )
    result = runner([*ssh_args(node, context), command], None)
    if (
        result.returncode != 0
        or result.stdout != "communications_cutover_preflight=verified\n"
        or result.stderr
    ):
        raise RuntimeError(
            "pinned communications cutover preflight did not prove off and drained"
        )
