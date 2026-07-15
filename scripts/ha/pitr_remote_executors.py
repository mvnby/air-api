"""Self-contained Python programs used by the pinned PITR SSH transport.

The values in this module are sent verbatim to ``python3 -I -c`` on a
production node.  They must therefore remain self-contained and must load
host-side helpers by their attested absolute paths.
"""

from __future__ import annotations

try:
    from scripts.ha.pitr_completion_attestation import (
        REMOTE_COMPLETION_ATTESTATION,
    )
    from scripts.ha.pitr_fenced_provision_remote import (
        FENCED_PROVISION_HELPERS,
    )
    from scripts.ha.pitr_remote_asset_attestation import (
        REMOTE_ASSET_ATTESTATION,
    )
    from scripts.ha.pitr_role_agent_process_attestation import (
        REMOTE_ROLE_AGENT_PROCESS_ATTESTATION,
    )
    from scripts.ha.pitr_role_agent_remote_executor import (
        REMOTE_ROLE_AGENT_EXECUTOR_BODY,
    )
except ModuleNotFoundError:  # Direct execution from scripts/ha.
    from pitr_completion_attestation import (  # type: ignore[no-redef]
        REMOTE_COMPLETION_ATTESTATION,
    )
    from pitr_fenced_provision_remote import (  # type: ignore[no-redef]
        FENCED_PROVISION_HELPERS,
    )
    from pitr_remote_asset_attestation import (  # type: ignore[no-redef]
        REMOTE_ASSET_ATTESTATION,
    )
    from pitr_role_agent_process_attestation import (  # type: ignore[no-redef]
        REMOTE_ROLE_AGENT_PROCESS_ATTESTATION,
    )
    from pitr_role_agent_remote_executor import (  # type: ignore[no-redef]
        REMOTE_ROLE_AGENT_EXECUTOR_BODY,
    )



LOCKED_OPERATION_WRAPPER = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + REMOTE_COMPLETION_ATTESTATION
    + "\n"
    + FENCED_PROVISION_HELPERS
    + "\n"
    + r'''
import sys

LOCK_PATH = "/run/lock/mvn-postgres-pitr-prerequisites.lock"
PROVISION_HELPER = "/usr/local/sbin/mvn-postgres-pitr-provision-host"
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
    completion_nonce = os.environ.get("PITR_COMPLETION_NONCE", "")
    completion_wrapper_digest = os.environ.get(
        "PITR_COMPLETION_WRAPPER_SHA256", ""
    )
    expected_unit = f"mvn-postgres-pitr-manual-{operation_id}.service"
    try:
        _completion_payload(
            completion_nonce,
            transaction_id,
            phase,
            project_dir,
            compose_file,
            asset_manifest,
            completion_wrapper_digest,
        )
    except RuntimeError as exc:
        return wrapper_fail(str(exc), 78)
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
            manifest = attest_assets(asset_manifest, project_dir, compose_file)
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
            "API_DEPLOY_LOCK_FD": "9",
            "API_DEPLOY_LOCK_FILE": os.path.join(project_dir, ".deploy.lock"),
            "API_DEPLOY_LOCK_HELPER": "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py",
            "API_DEPLOY_LOCK_HELPER_SHA256": manifest[
                "/usr/local/libexec/mvn-pitr/safe_deploy_lock.py"
            ],
        }
        secret_fd = None
        payload = None
        payload_view = None
        try:
            if deploy_fd != 9:
                os.dup2(deploy_fd, 9, inheritable=True)
                os.close(deploy_fd)
                deploy_fd = 9
            else:
                os.set_inheritable(deploy_fd, True)
            pass_fds = (deploy_fd,)
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
                pass_fds = (deploy_fd, secret_fd)
            provision_mode = os.environ.get("PITR_PROVISION_MODE", "standard")
            if provision_mode not in {"standard", "fenced"}:
                return wrapper_fail("invalid PITR provision mode", 78)
            if provision_mode == "fenced" and phase != "provision-node":
                return wrapper_fail("fenced mode requires provision-node", 78)
            command = [bootstrap_helper, phase]
            if provision_mode == "fenced":
                prove_fenced_provision_state(project_dir, compose_file)
                command = [
                    PROVISION_HELPER,
                    "--project-dir",
                    project_dir,
                    "--compose-file",
                    compose_file,
                    "--transaction-id",
                    transaction_id,
                ]
            result = subprocess.run(
                command,
                env=environment,
                check=False,
                pass_fds=pass_fds,
            )
            return write_completion_after_status(
                result.returncode,
                completion_nonce,
                transaction_id,
                phase,
                project_dir,
                compose_file,
                asset_manifest,
                completion_wrapper_digest,
            )
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


REMOTE_ROLE_AGENT_EXECUTOR = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + REMOTE_ROLE_AGENT_PROCESS_ATTESTATION
    + "\n"
    + REMOTE_ROLE_AGENT_EXECUTOR_BODY
).strip()


REMOTE_SECRET_EXECUTOR = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + REMOTE_COMPLETION_ATTESTATION
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
            if guard.list_records(project_dir=project_dir):
                return fail("another recorded PITR operation requires cleanup", 75)
            scavenge_completion_receipts()
        except (OSError, RuntimeError) as exc:
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
    completion_nonce = secrets.token_hex(16)
    environment["PITR_COMPLETION_NONCE"] = completion_nonce
    environment["PITR_COMPLETION_WRAPPER_SHA256"] = locked_wrapper_digest
    payload_view = memoryview(payload)
    try:
        status = run_bounded(
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
            operation_id=transaction_id,
        )
        if status != 0:
            return status
        try:
            status = consume_completion_after_status(
                status,
                completion_nonce,
                transaction_id,
                phase,
                project_dir,
                compose_file,
                asset_manifest,
                locked_wrapper_digest,
            )
        except (OSError, RuntimeError) as exc:
            return fail(f"completion attestation failed: {exc}", 78)
        return status
    finally:
        try:
            discard_completion_receipt(
                completion_nonce,
                transaction_id,
                phase,
                project_dir,
                compose_file,
                asset_manifest,
                locked_wrapper_digest,
            )
        except (OSError, RuntimeError):
            pass
        payload_view[:] = b"\0" * len(payload_view)
        payload_view.release()


raise SystemExit(main())
'''
).strip()


REMOTE_MAINTENANCE_EXECUTOR = (
    REMOTE_ASSET_ATTESTATION
    + "\n"
    + REMOTE_COMPLETION_ATTESTATION
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
    if confirmed not in {"false", "fenced"}:
        return fail("unexpected maintenance confirmation value", 64)
    if confirmed == "fenced" and phase != "provision-node":
        return fail("fenced confirmation requires provision-node", 64)
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
            if guard.list_records(project_dir=project_dir):
                return fail("another recorded PITR operation requires cleanup", 75)
            scavenge_completion_receipts()
        except (OSError, RuntimeError) as exc:
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
        "PITR_PROVISION_MODE": "fenced" if confirmed == "fenced" else "standard",
    }
    completion_nonce = secrets.token_hex(16)
    environment["PITR_COMPLETION_NONCE"] = completion_nonce
    environment["PITR_COMPLETION_WRAPPER_SHA256"] = locked_wrapper_digest
    try:
        status = run_bounded(
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
            operation_id=transaction_id,
        )
        if status != 0:
            return status
        try:
            status = consume_completion_after_status(
                status,
                completion_nonce,
                transaction_id,
                phase,
                project_dir,
                compose_file,
                asset_manifest,
                locked_wrapper_digest,
            )
        except (OSError, RuntimeError) as exc:
            return fail(f"completion attestation failed: {exc}", 78)
        return status
    finally:
        try:
            discard_completion_receipt(
                completion_nonce,
                transaction_id,
                phase,
                project_dir,
                compose_file,
                asset_manifest,
                locked_wrapper_digest,
            )
        except (OSError, RuntimeError):
            pass


raise SystemExit(main())
'''
).strip()
