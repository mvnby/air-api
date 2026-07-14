"""Self-contained Python programs used by the pinned PITR SSH transport.

The values in this module are sent verbatim to ``python3 -I -c`` on a
production node.  They must therefore remain self-contained and must load
host-side helpers by their attested absolute paths.
"""

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
):
    guard = guard_module or load_operation_guard()
    if guard.list_records(project_dir=project_dir):
        raise RuntimeError("another recorded PITR operation requires cleanup")
    operation_id = secrets.token_hex(16)
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
'''.strip()


LOCKED_OPERATION_WRAPPER = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + r'''
import sys

LOCK_PATH = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
MAX_PAYLOAD_BYTES = 65536
SECRET_PHASES = {"preflight", "configure-node"}
MAINTENANCE_PHASES = {
    "provision-node",
    "scrub-node",
    "basebackup",
    "enable-archive-env",
    "enable-timers",
    "restore-drill",
    "verify",
}
ALLOWED_PHASES = SECRET_PHASES | MAINTENANCE_PHASES


def wrapper_fail(message, status=70):
    print(f"locked PITR operation: {message}", file=sys.stderr)
    return status


def wrapper_main():
    if len(sys.argv) != 7:
        return wrapper_fail("invalid invocation", 64)
    (
        bootstrap_helper,
        phase,
        project_dir,
        compose_file,
        transaction_id,
        asset_manifest,
    ) = sys.argv[1:]
    if os.geteuid() != 0:
        return wrapper_fail("root execution is required", 77)
    if bootstrap_helper != "/usr/local/sbin/mvn-postgres-pitr-bootstrap":
        return wrapper_fail("unexpected bootstrap helper path", 64)
    if phase not in ALLOWED_PHASES:
        return wrapper_fail("unsupported operation phase", 64)
    if re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        return wrapper_fail("invalid PITR transaction ID", 64)
    if phase in SECRET_PHASES and not hasattr(os, "memfd_create"):
        return wrapper_fail("required Linux secret transport is unavailable", 78)
    operation_id = os.environ.get("PITR_OPERATION_ID", "")
    expected_unit = f"mvn-postgres-pitr-manual-{operation_id}.service"
    os.umask(0o077)
    lock_fd = os.open(
        LOCK_PATH,
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    deploy_fd = None
    try:
        lock_metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != 0
            or lock_metadata.st_nlink != 1
        ):
            return wrapper_fail("shared PITR lock metadata is unsafe", 78)
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return wrapper_fail("another PITR operation is active", 75)
        try:
            deploy_fd = open_deploy_lock(project_dir)
        except BlockingIOError:
            return wrapper_fail("a project deployment is active", 75)
        except RuntimeError as exc:
            return wrapper_fail(str(exc), 78)
        try:
            attest_assets(asset_manifest, project_dir, compose_file)
            guard = load_operation_guard()
            records = guard.list_records(project_dir=project_dir)
            if (
                len(records) != 1
                or records[0].operation_id != operation_id
                or records[0].unit != expected_unit
                or records[0].phase != phase
            ):
                return wrapper_fail("operation record does not match the transient unit", 78)
        except RuntimeError as exc:
            return wrapper_fail(str(exc), 78)
        environment = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "HOME": "/root",
            "LANG": "C",
            "LC_ALL": "C",
            "DOCKER_CONTEXT": "default",
            "PROJECT_DIR": project_dir,
            "COMPOSE_FILE": compose_file,
            "PITR_OPERATION_ID": operation_id,
            "PITR_TRANSACTION_ID": transaction_id,
        }
        secret_fd = None
        payload = None
        payload_view = None
        try:
            pass_fds = ()
            if phase in SECRET_PHASES:
                payload = bytearray(sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1))
                if not payload or len(payload) > MAX_PAYLOAD_BYTES:
                    return wrapper_fail("secret payload size is invalid", 65)
                secret_fd = os.memfd_create(
                    "mvn-postgres-pitr-env",
                    flags=os.MFD_ALLOW_SEALING | os.MFD_CLOEXEC,
                )
                os.fchmod(secret_fd, 0o600)
                payload_view = memoryview(payload)
                offset = 0
                while offset < len(payload_view):
                    written = os.write(secret_fd, payload_view[offset:])
                    if written <= 0:
                        return wrapper_fail("could not stage secret payload")
                    offset += written
                os.lseek(secret_fd, 0, os.SEEK_SET)
                fcntl.fcntl(
                    secret_fd,
                    fcntl.F_ADD_SEALS,
                    fcntl.F_SEAL_WRITE
                    | fcntl.F_SEAL_GROW
                    | fcntl.F_SEAL_SHRINK
                    | fcntl.F_SEAL_SEAL,
                )
                environment["ENV_INPUT_FILE"] = f"/proc/self/fd/{secret_fd}"
                pass_fds = (secret_fd,)
            result = subprocess.run(
                [bootstrap_helper, phase],
                env=environment,
                check=False,
                pass_fds=pass_fds,
            )
            return result.returncode
        finally:
            if payload_view is not None:
                payload_view[:] = b"\0" * len(payload_view)
                payload_view.release()
            if secret_fd is not None:
                os.close(secret_fd)
    finally:
        if deploy_fd is not None:
            os.close(deploy_fd)
        os.close(lock_fd)


raise SystemExit(wrapper_main())
'''
).strip()

# Backward-compatible export for callers/tests while both phase families share
# one cgroup-owning, lock-owning wrapper.
LOCKED_MAINTENANCE_WRAPPER = LOCKED_OPERATION_WRAPPER


REMOTE_SECRET_EXECUTOR = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + r'''
import subprocess
import sys

MAX_PAYLOAD_BYTES = 65536
LOCK_PATH = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
ALLOWED_PHASES = {"preflight", "configure-node"}


def fail(message, status=70):
    print(f"pitr secret executor: {message}", file=sys.stderr)
    return status


def main():
    if len(sys.argv) != 9:
        return fail("invalid invocation", 64)
    if os.geteuid() != 0:
        return fail("root execution is required", 77)
    if not hasattr(os, "O_NOFOLLOW"):
        return fail("required lock protection is unavailable")
    (
        bootstrap_helper,
        phase,
        project_dir,
        compose_file,
        transaction_id,
        asset_manifest,
        locked_wrapper,
        locked_wrapper_digest,
    ) = sys.argv[1:]
    if bootstrap_helper != "/usr/local/sbin/mvn-postgres-pitr-bootstrap":
        return fail("unexpected bootstrap helper path", 64)
    if phase not in ALLOWED_PHASES:
        return fail("unsupported secret phase", 64)
    if re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        return fail("invalid PITR transaction ID", 64)
    if hashlib.sha256(locked_wrapper.encode()).hexdigest() != locked_wrapper_digest:
        return fail("locked operation wrapper digest mismatch", 78)
    payload = bytearray(sys.stdin.buffer.read(MAX_PAYLOAD_BYTES + 1))
    if not payload or len(payload) > MAX_PAYLOAD_BYTES:
        return fail("secret payload size is invalid", 65)
    os.umask(0o077)
    lock_flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    lock_fd = os.open(LOCK_PATH, lock_flags, 0o600)
    deploy_fd = None
    try:
        lock_metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.geteuid()
            or lock_metadata.st_nlink != 1
        ):
            return fail("lock file metadata is unsafe")
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return fail("another PITR prerequisite apply is active", 75)
        try:
            deploy_fd = open_deploy_lock(project_dir)
        except BlockingIOError:
            return fail("a project deployment is active", 75)
        except RuntimeError as exc:
            return fail(str(exc), 78)
        try:
            attest_assets(asset_manifest, project_dir, compose_file)
            guard = load_operation_guard()
        except RuntimeError as exc:
            return fail(str(exc), 78)
    finally:
        if deploy_fd is not None:
            os.close(deploy_fd)
        os.close(lock_fd)
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C",
        "LC_ALL": "C",
        "DOCKER_CONTEXT": "default",
        "PROJECT_DIR": project_dir,
        "COMPOSE_FILE": compose_file,
    }
    payload_view = memoryview(payload)
    try:
        return run_bounded(
            [
                "/usr/bin/python3",
                "-I",
                "-c",
                locked_wrapper,
                bootstrap_helper,
                phase,
                project_dir,
                compose_file,
                transaction_id,
                asset_manifest,
            ],
            environment=environment,
            pass_fds=(),
            phase=phase,
            project_dir=project_dir,
            timeout_seconds={
                "preflight": 900,
                "configure-node": 900,
            }[phase],
            transient=True,
            record_command=bootstrap_helper,
            stdin_payload=payload_view,
            guard_module=guard,
        )
    finally:
        payload_view[:] = b"\0" * len(payload_view)
        payload_view.release()


raise SystemExit(main())
'''
).strip()


REMOTE_MAINTENANCE_EXECUTOR = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + r'''
import subprocess
import sys

LOCK_PATH = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
ALLOWED_PHASES = {
    "provision-node",
    "scrub-node",
    "basebackup",
    "enable-archive-env",
    "enable-timers",
    "restore-drill",
    "verify",
}


def fail(message, status=70):
    print(f"pitr maintenance executor: {message}", file=sys.stderr)
    return status


def main():
    if len(sys.argv) != 10:
        return fail("invalid invocation", 64)
    if os.geteuid() != 0:
        return fail("root execution is required", 77)
    if not hasattr(os, "O_NOFOLLOW"):
        return fail("required lock protection is unavailable")
    (
        bootstrap_helper,
        phase,
        project_dir,
        compose_file,
        confirmed,
        transaction_id,
        asset_manifest,
        locked_wrapper,
        locked_wrapper_digest,
    ) = sys.argv[1:]
    if bootstrap_helper != "/usr/local/sbin/mvn-postgres-pitr-bootstrap":
        return fail("unexpected bootstrap helper path", 64)
    if phase not in ALLOWED_PHASES:
        return fail("unsupported maintenance phase", 64)
    if confirmed != "false":
        return fail("unexpected maintenance confirmation value", 64)
    if re.fullmatch(r"[0-9a-f]{32}", transaction_id) is None:
        return fail("invalid PITR transaction ID", 64)
    if hashlib.sha256(locked_wrapper.encode()).hexdigest() != locked_wrapper_digest:
        return fail("locked maintenance wrapper digest mismatch", 78)
    os.umask(0o077)
    lock_flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    lock_fd = os.open(LOCK_PATH, lock_flags, 0o600)
    try:
        lock_metadata = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_metadata.st_mode)
            or lock_metadata.st_uid != os.geteuid()
            or lock_metadata.st_nlink != 1
        ):
            return fail("lock file metadata is unsafe")
        os.fchmod(lock_fd, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return fail("another PITR prerequisite apply is active", 75)
        try:
            attest_assets(asset_manifest, project_dir, compose_file)
            guard = load_operation_guard()
        except RuntimeError as exc:
            return fail(str(exc), 78)
    finally:
        os.close(lock_fd)
    environment = {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "HOME": "/root",
        "LANG": "C",
        "LC_ALL": "C",
        "DOCKER_CONTEXT": "default",
        "PROJECT_DIR": project_dir,
        "COMPOSE_FILE": compose_file,
    }
    return run_bounded(
        [
            "/usr/bin/python3",
            "-I",
            "-c",
            locked_wrapper,
            bootstrap_helper,
            phase,
            project_dir,
            compose_file,
            transaction_id,
            asset_manifest,
        ],
        environment=environment,
        pass_fds=(),
        phase=phase,
        project_dir=project_dir,
        timeout_seconds={
            "provision-node": 900,
            "scrub-node": 1800,
            "basebackup": 7200,
            "enable-archive-env": 900,
            "enable-timers": 900,
            "verify": 1200,
            "restore-drill": 7200,
        }[phase],
        transient=True,
        record_command=bootstrap_helper,
        guard_module=guard,
    )


raise SystemExit(main())
'''
).strip()
